"""阶段2：把对话做成 HTTP 接口（任何前端/设备都能连）。

启动：
    uvicorn api_server:app --host 0.0.0.0 --port 8000
然后浏览器打开 http://127.0.0.1:8000/docs 直接测试 /chat

接口一览：
    POST /chat         —— 一次性返回完整回复（简单，延迟高）
    POST /chat/stream  —— 流式返回（SSE，边生成边吐字，设备/前端体验更好）
    POST /agent        —— 能调工具的版本（查时间/天气、做计算，从"会聊"到"能办事"）
    POST /voice        —— 语音进语音出（收 WAV → STT → 大模型 → TTS → 回 WAV），给设备用
    GET  /             —— 健康检查
"""
import os
import json
import asyncio
import urllib.parse

import config
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from openai import AsyncOpenAI, OpenAIError

import tools  # 工具定义 + 调用闭环（与命令行版 agent.py 共用）
import store  # 会话持久化（SQLite，重启不丢记忆）
import resilience  # 上游调用：并发限流 + 指数退避重试

store.init()

# 全异步：用 AsyncOpenAI，端点 async def，模型调用 await。多请求的网络等待可真正
# 重叠，事件循环不被阻塞；STT/TTS 等阻塞调用用 asyncio.to_thread 卸载到线程池。
aclient = AsyncOpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
app = FastAPI(title="AI 对话机器人")

# 边缘背压：在途请求过多时直接 429 快速失败，保护服务不被压垮（限流第二道防线）。
# asyncio 单线程事件循环里，计数器的读改写之间没有 await，天然原子，无需加锁。
MAX_INFLIGHT = int(os.getenv("XZ_MAX_INFLIGHT", "32"))
_inflight = 0


@app.middleware("http")
async def backpressure(request: Request, call_next):
    global _inflight
    if _inflight >= MAX_INFLIGHT:
        return JSONResponse(status_code=429,
                            content={"detail": "服务繁忙，请稍后重试"})
    _inflight += 1
    try:
        return await call_next(request)
    finally:
        _inflight -= 1


SYSTEM = "你是一个友好、简洁的中文 AI 助手，名字叫小智。"
AGENT_SYSTEM = tools.AGENT_SYSTEM   # 单一真相源在 tools.py，评测与服务端共用
MODEL = "qwen-flash"

# 每个会话一条消息历史。内存 dict 当缓存，背后用 SQLite 持久化（store.py）：
# 没命中缓存就从库里加载，每轮结束写回库，进程重启后记忆还在。
# 普通对话与 Agent 各用一个命名空间(ns)，避免两种 system 人设互相串。
SESSIONS: dict[str, list] = {}
AGENT_SESSIONS: dict[str, list] = {}
VOICE_SESSIONS: dict[str, list] = {}
NS_CHAT = "chat"
NS_AGENT = "agent"
NS_VOICE = "voice"

# 语音助手专用人设：口语化、不带 emoji（会被读出来）。
VOICE_SYSTEM = (
    "你是一个友好、生动的中文语音助手，名字叫小智，说话自然、简洁、有感情。"
    "日常问答两三句话即可，别啰嗦。不要使用任何表情符号(emoji)，因为你的回答会被读出来。"
)

# 上下文上限：每个会话最多保留最近 MAX_TURNS 轮（1 轮 = 1 问 + 1 答）。
# 超过就丢掉最老的几轮，防止对话越长 token 越多以致超限/烧钱。system 永远保留。
MAX_TURNS = 10


class ChatRequest(BaseModel):
    session_id: str = "default"   # 不同设备/用户用不同 id，互不串话
    message: str


def get_history(session_id: str, mem: dict, system: str, ns: str) -> list:
    """取某会话的消息历史：先查内存缓存，再查库，都没有才新建。"""
    if session_id in mem:
        return mem[session_id]
    loaded = store.load(ns, session_id)
    msgs = loaded if loaded else [{"role": "system", "content": system}]
    mem[session_id] = msgs
    return msgs


def trim_history(msgs: list) -> None:
    """原地压缩历史：保留 system + 最近 MAX_TURNS 轮（2*MAX_TURNS 条消息）。"""
    keep = 2 * MAX_TURNS
    if len(msgs) > keep + 1:          # +1 是 system
        # msgs[0] 是 system，其余只留末尾 keep 条
        del msgs[1:len(msgs) - keep]


async def acall_model(msgs: list, stream: bool):
    """统一封装异步模型调用：并发限流 + 退避重试；异常转 HTTP 502，避免裸 500。"""
    try:
        return await resilience.acall(lambda: aclient.chat.completions.create(
            model=MODEL, messages=msgs, temperature=0.7, stream=stream,
        ))
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"上游模型调用失败：{e}")


@app.post("/chat")
async def chat(req: ChatRequest):
    """一次性返回完整回复。"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    msgs = get_history(req.session_id, SESSIONS, SYSTEM, NS_CHAT)
    msgs.append({"role": "user", "content": req.message})
    trim_history(msgs)

    resp = await acall_model(msgs, stream=False)
    reply = resp.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    store.save(NS_CHAT, req.session_id, msgs)
    return {"reply": reply}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式返回：Server-Sent Events，每个增量一行 `data: {"delta": "..."}`。

    客户端（含单片机）按行读取，遇到 `data: [DONE]` 表示结束。
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    msgs = get_history(req.session_id, SESSIONS, SYSTEM, NS_CHAT)
    msgs.append({"role": "user", "content": req.message})
    trim_history(msgs)

    async def event_stream():
        reply = ""
        try:
            stream = await acall_model(msgs, stream=True)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    reply += delta
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except HTTPException as e:
            yield f"data: {json.dumps({'error': e.detail}, ensure_ascii=False)}\n\n"
        finally:
            # 只把成功生成的部分写回历史并持久化，保证记忆连贯
            if reply:
                msgs.append({"role": "assistant", "content": reply})
                store.save(NS_CHAT, req.session_id, msgs)
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/agent")
async def agent(req: ChatRequest):
    """能办事的版本：模型按需调用工具（时间/天气/计算），再给出最终回答。"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    msgs = get_history(req.session_id, AGENT_SESSIONS, AGENT_SYSTEM, NS_AGENT)
    msgs.append({"role": "user", "content": req.message})
    trim_history(msgs)

    used: list = []   # 记录这次实际调了哪些工具，方便前端/设备展示
    try:
        reply = await tools.run_with_tools_async(
            aclient, MODEL, msgs,
            on_tool=lambda name, args, result: used.append(
                {"name": name, "args": args, "result": result}
            ),
            session_id=req.session_id,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"上游模型调用失败：{e}")
    store.save(NS_AGENT, req.session_id, msgs)
    return {"reply": reply, "tools_used": used}


@app.post("/voice")
async def voice(request: Request):
    """语音进、语音出：收设备录的 WAV → 听懂 → 想 → 说成 WAV 回去。

    请求：Body=WAV(16k/16bit/单声道)，Header `X-Session-Id` 区分设备。
    返回：Body=WAV(16k/16bit/单声道)；Header `X-Reply-Text` 是回复文本(URL编码)。
    """
    # 惰性导入：没装语音依赖(dashscope)时，基础服务仍可启动，只有本接口报 503。
    try:
        import voice_server as vs
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"语音依赖未安装，请 pip install -r requirements-voice.txt（{e}）")

    wav_in = await request.body()
    if not wav_in:
        raise HTTPException(status_code=400, detail="请求体为空，应为 WAV 音频")
    session_id = request.headers.get("X-Session-Id", "default")

    try:
        # 1) 听：STT（阻塞的网络调用，卸载到线程池，避免堵住事件循环）
        text = (await asyncio.to_thread(vs.stt_from_bytes, wav_in)).strip()
        if not text:
            # 没听清也回一句语音，体验更好
            wav_out = await asyncio.to_thread(vs.tts_wav, "我没听清，请再说一次。")
            return Response(content=wav_out, media_type="audio/wav",
                            headers={"X-Reply-Text": urllib.parse.quote("我没听清，请再说一次。")})

        # 2) 想：带记忆地问大模型（语音人设 + 持久化）
        msgs = get_history(session_id, VOICE_SESSIONS, VOICE_SYSTEM, NS_VOICE)
        msgs.append({"role": "user", "content": text})
        trim_history(msgs)
        resp = await acall_model(msgs, stream=False)
        reply = resp.choices[0].message.content
        msgs.append({"role": "assistant", "content": reply})
        store.save(NS_VOICE, session_id, msgs)

        # 3) 说：TTS → WAV（同样卸载到线程池）
        wav_out = await asyncio.to_thread(vs.tts_wav, reply)
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"上游模型调用失败：{e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音处理出错：{e}")

    # 文本放 Header 方便设备显示/调试；中文要 URL 编码，否则 Header 不能带非 ASCII。
    return Response(content=wav_out, media_type="audio/wav",
                    headers={"X-Reply-Text": urllib.parse.quote(reply)})


@app.get("/")
def health():
    return {"status": "ok"}
