"""阶段2：把对话做成 HTTP 接口（任何前端/设备都能连）。

启动：
    uvicorn api_server:app --host 0.0.0.0 --port 8000
然后浏览器打开 http://127.0.0.1:8000/docs 直接测试 /chat

接口一览：
    POST /chat         —— 一次性返回完整回复（简单，延迟高）
    POST /chat/stream  —— 流式返回（SSE，边生成边吐字，设备/前端体验更好）
    POST /agent        —— 能调工具的版本（查时间/天气、做计算，从"会聊"到"能办事"）
    GET  /             —— 健康检查
"""
import os
import json

import config
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI, OpenAIError

import tools  # 工具定义 + 调用闭环（与命令行版 agent.py 共用）
import store  # 会话持久化（SQLite，重启不丢记忆）

store.init()

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
app = FastAPI(title="AI 对话机器人")
SYSTEM = "你是一个友好、简洁的中文 AI 助手，名字叫小智。"
AGENT_SYSTEM = (
    "你是一个会使用工具的中文助手，名字叫小智。"
    "需要实时信息（时间、天气）或精确计算时，优先调用工具，不要凭空编造。"
    "拿到工具结果后，用自然、简洁的中文把答案讲给用户。"
)
MODEL = "qwen-flash"

# 每个会话一条消息历史。内存 dict 当缓存，背后用 SQLite 持久化（store.py）：
# 没命中缓存就从库里加载，每轮结束写回库，进程重启后记忆还在。
# 普通对话与 Agent 各用一个命名空间(ns)，避免两种 system 人设互相串。
SESSIONS: dict[str, list] = {}
AGENT_SESSIONS: dict[str, list] = {}
NS_CHAT = "chat"
NS_AGENT = "agent"

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


def call_model(msgs: list, stream: bool):
    """统一封装模型调用，把 SDK 异常转成 HTTP 502，避免裸 500。"""
    try:
        return client.chat.completions.create(
            model=MODEL, messages=msgs, temperature=0.7, stream=stream,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"上游模型调用失败：{e}")


@app.post("/chat")
def chat(req: ChatRequest):
    """一次性返回完整回复。"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    msgs = get_history(req.session_id, SESSIONS, SYSTEM, NS_CHAT)
    msgs.append({"role": "user", "content": req.message})
    trim_history(msgs)

    resp = call_model(msgs, stream=False)
    reply = resp.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    store.save(NS_CHAT, req.session_id, msgs)
    return {"reply": reply}


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """流式返回：Server-Sent Events，每个增量一行 `data: {"delta": "..."}`。

    客户端（含单片机）按行读取，遇到 `data: [DONE]` 表示结束。
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    msgs = get_history(req.session_id, SESSIONS, SYSTEM, NS_CHAT)
    msgs.append({"role": "user", "content": req.message})
    trim_history(msgs)

    def event_stream():
        reply = ""
        try:
            stream = call_model(msgs, stream=True)
            for chunk in stream:
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
def agent(req: ChatRequest):
    """能办事的版本：模型按需调用工具（时间/天气/计算），再给出最终回答。"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    msgs = get_history(req.session_id, AGENT_SESSIONS, AGENT_SYSTEM, NS_AGENT)
    msgs.append({"role": "user", "content": req.message})
    trim_history(msgs)

    used: list = []   # 记录这次实际调了哪些工具，方便前端/设备展示
    try:
        reply = tools.run_with_tools(
            client, MODEL, msgs,
            on_tool=lambda name, args, result: used.append(
                {"name": name, "args": args, "result": result}
            ),
        )
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"上游模型调用失败：{e}")
    store.save(NS_AGENT, req.session_id, msgs)
    return {"reply": reply, "tools_used": used}


@app.get("/")
def health():
    return {"status": "ok"}
