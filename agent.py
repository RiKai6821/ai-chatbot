"""进阶：工具调用（function calling）最小示例 —— 从"会聊天"到"能办事"。

核心思想：
  你把若干"工具"（函数）的说明书交给模型，模型在需要时**自己决定**调用哪个、
  传什么参数。它不直接执行函数——而是返回一个"我想调用 X(参数)"的请求，
  由我们（Python）真正执行，再把结果喂回去，模型据此给出最终自然语言回答。

闭环（关键）：
  用户提问 → 模型说"调 get_weather(北京)" → 我们执行拿到结果 → 回填给模型
           → 模型可能再调别的，也可能直接给出最终回答。循环直到不再调工具。

工具定义和闭环都在 tools.py 里（HTTP 版 api_server.py 也复用同一套）。
本文件只负责命令行交互。

运行：
    .\\venv\\Scripts\\python.exe agent.py
试试问：
    现在几点？        北京天气怎么样？      帮我算一下 (23*19+7)/2 等于多少？
    先看看上海天气，再算 100 减去当前的小时数
"""
import os

import config  # 自动加载 .env
from openai import OpenAI

import tools

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

SYSTEM = (
    "你是一个会使用工具的中文助手，名字叫小智。"
    "需要实时信息（时间、天气）或精确计算时，优先调用工具，不要凭空编造。"
    "拿到工具结果后，用自然、简洁的中文把答案讲给用户。"
)
MODEL = "qwen-flash"


def _show_tool(name, args, result):
    print(f"  [调用工具 {name}({args}) -> {result}]")


def main():
    messages = [{"role": "system", "content": SYSTEM}]
    print("能办事的小智已就绪（输入 quit 退出）。试试：现在几点？/ 北京天气？/ 算 (23*19+7)/2")
    while True:
        user = input("\n你：").strip()
        if user.lower() in ("quit", "exit", "q"):
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        reply = tools.run_with_tools(client, MODEL, messages, on_tool=_show_tool)
        print(f"小智：{reply}")


if __name__ == "__main__":
    main()
