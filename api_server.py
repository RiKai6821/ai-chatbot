"""阶段2：把对话做成 HTTP 接口（任何前端/设备都能连）。

启动：
    uvicorn api_server:app --host 0.0.0.0 --port 8000
然后浏览器打开 http://127.0.0.1:8000/docs 直接测试 /chat
"""
import os
import config
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
app = FastAPI(title="AI 对话机器人")
SYSTEM = "你是一个友好、简洁的中文 AI 助手，名字叫小智。"

# 每个会话一条消息历史（生产环境应换成 Redis/数据库）
SESSIONS: dict[str, list] = {}


class ChatRequest(BaseModel):
    session_id: str = "default"   # 不同设备/用户用不同 id，互不串话
    message: str


@app.post("/chat")
def chat(req: ChatRequest):
    msgs = SESSIONS.setdefault(
        req.session_id, [{"role": "system", "content": SYSTEM}]
    )
    msgs.append({"role": "user", "content": req.message})
    resp = client.chat.completions.create(
        model="qwen-flash", messages=msgs, temperature=0.7,
    )
    reply = resp.choices[0].message.content
    msgs.append({"role": "assistant", "content": reply})
    return {"reply": reply}


@app.get("/")
def health():
    return {"status": "ok"}
