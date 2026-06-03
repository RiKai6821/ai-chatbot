"""阶段0 / 阶段1：命令行多轮对话。

- messages 列表就是"记忆"：每轮把用户和 AI 的话都存进去，模型才能记得前文。
- STREAM=True 开启流式输出（边生成边显示，体验更像真人）。
"""
import os
import config  # 自动加载 .env
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

SYSTEM = "你是一个友好、简洁的中文 AI 助手，名字叫小智。"
MODEL = "qwen-flash"   # 便宜快；要更聪明用 qwen-plus
STREAM = True          # 阶段1：流式输出；设为 False 即阶段0 一次性返回
MAX_TURNS = 10         # 上下文上限：只保留最近 N 轮，防止对话越长越烧 token


def reply_once(messages) -> str:
    """非流式：一次性拿到完整回复。"""
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.7,
    )
    reply = resp.choices[0].message.content
    print(f"小智：{reply}")
    return reply


def reply_stream(messages) -> str:
    """流式：文字逐字蹦出来。"""
    stream = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.7, stream=True,
    )
    reply = ""
    print("小智：", end="", flush=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
            reply += delta
    print()
    return reply


def trim_history(messages) -> None:
    """原地压缩历史：保留 system + 最近 MAX_TURNS 轮（2*MAX_TURNS 条消息）。"""
    keep = 2 * MAX_TURNS
    if len(messages) > keep + 1:        # +1 是 system
        del messages[1:len(messages) - keep]


def main():
    messages = [{"role": "system", "content": SYSTEM}]
    print("开始对话（输入 quit 退出）")
    while True:
        user = input("\n你：").strip()
        if user.lower() in ("quit", "exit", "q"):
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        trim_history(messages)          # 发请求前先裁掉过老的历史
        reply = reply_stream(messages) if STREAM else reply_once(messages)
        messages.append({"role": "assistant", "content": reply})  # 记住上下文


if __name__ == "__main__":
    main()
