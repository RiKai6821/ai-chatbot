"""工具定义 + 工具调用闭环（被 agent.py 和 api_server.py 共用）。

这里集中放：能干活的函数、交给模型的"工具说明书"、以及执行闭环 run_with_tools。
想加新能力，只改这一个文件，命令行版和 HTTP 版会同时拥有。

加一个新工具只需 3 步：
  1) 写一个普通 Python 函数；
  2) 在 DISPATCH 里登记 名字 -> 函数；
  3) 在 TOOLS 里加一段 JSON 说明书（description 写清楚"何时调、参数啥意思"）。
"""
import json
import math
import time
import asyncio
import datetime

import tracing  # 结构化追踪（自动给每轮对话/工具调用打 JSON 日志）

MAX_TOOL_ROUNDS = 5   # 一次提问里最多连续调几次工具，防死循环

# Agent 人设（服务端 /agent 与评测共用，单一真相源）。
AGENT_SYSTEM = (
    "你是一个会使用工具的中文助手，名字叫小智。"
    "需要实时信息（时间、天气）或精确计算时，优先调用对应工具，不要凭空编造。"
    "涉及小智产品本身（规格、常见问题、保修售后等）时，先用 search_knowledge 检索知识库再回答。"
    "拿到工具结果后，用自然、简洁的中文把答案讲给用户。"
)


# ── 1) 真正干活的函数 ──────────────────────────────────────
def get_current_time() -> str:
    """返回当前日期时间（真实，无需任何 API Key）。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calculate(expression: str) -> str:
    """安全地计算一个数学表达式，例如 '(23*19+7)/2'。"""
    # 只放行数学相关的名字，禁用内建函数，避免 eval 被滥用。
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update(abs=abs, round=round, min=min, max=max)
    try:
        return str(eval(expression, {"__builtins__": {}}, allowed))
    except Exception as e:
        return f"计算失败：{e}"


def get_weather(city: str) -> str:
    """查询城市天气。

    这里用假数据演示"调用外部 API"的形态——真实项目里把这段换成
    requests.get("https://真实天气API?city=...") 解析返回即可，调用方式不变。
    """
    fake = {
        "北京": "晴，12~24℃，微风",
        "上海": "多云，16~22℃，东风3级",
        "广州": "阵雨，24~29℃，闷热",
    }
    return fake.get(city, f"暂无 {city} 的天气数据（这是演示用的假数据）")


def search_knowledge(query: str) -> str:
    """从私有知识库检索（RAG）。问到产品规格/FAQ/保修等资料时用，避免瞎编。"""
    import rag  # 惰性导入：不用 RAG 时不触发建索引/网络
    hits = rag.search(query, k=3)
    if not hits:
        return "知识库里没有找到相关内容。"
    return "\n\n".join(f"[来源:{h['source']}] {h['text']}" for h in hits)


# 名字 → 函数 的分发表
DISPATCH = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "get_weather": get_weather,
    "search_knowledge": search_knowledge,
}


# ── 2) 交给模型的"工具说明书"（JSON Schema）──────────────────
# description 和参数说明写得越清楚，模型越知道"何时调、怎么传"。
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间。当用户问现在几点、今天几号等需要实时时间时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算一个数学表达式并返回结果。涉及精确算术时调用，不要自己心算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "合法的数学表达式，如 (23*19+7)/2、sqrt(2)、2**10",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气。用户问某地天气时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如 北京、上海"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "从小智产品的私有知识库检索资料（产品规格、常见问题FAQ、保修售后政策等）。"
                "当用户问到这些设备/产品相关信息时，先调用它拿到依据，再据此回答，不要凭空编造。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要检索的问题或关键词"}
                },
                "required": ["query"],
            },
        },
    },
]


# ── 3) 工具调用闭环 ────────────────────────────────────────
def run_tool(name: str, args: dict) -> str:
    """按名字执行本地函数，返回字符串结果（喂回给模型）。"""
    fn = DISPATCH.get(name)
    if fn is None:
        return f"未知工具：{name}"
    try:
        return str(fn(**args))
    except Exception as e:
        return f"工具 {name} 执行出错：{e}"


def _assistant_msg(msg) -> dict:
    """把模型返回的 tool_calls 这条 assistant 消息转成可回填进 messages 的 dict。"""
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ],
    }


def run_with_tools(client, model, messages, on_tool=None, session_id="-") -> str:
    """让模型回答；若它要求调工具，就执行并回填，循环到给出最终文字答案。

    messages 会被原地追加（assistant / tool 消息），调用方拿它即可作为"记忆"。
    on_tool(name, args, result): 可选回调，用于打印/日志。
    session_id: 仅用于结构化追踪，便于按会话检索日志。
    返回最终的自然语言回答文本。

    全程自动打 JSON 结构化日志（见 trace.py）：模型调用次数、token、每次工具
    调用的名/参数/结果/耗时、整轮延迟。
    """
    turn = tracing.start_turn(session_id, messages[-1]["content"] if messages else "", model)
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=model, messages=messages, tools=TOOLS, temperature=0.7,
            )
            turn.add_model_call(getattr(resp, "usage", None))
            msg = resp.choices[0].message

            if not msg.tool_calls:
                # 没有要调工具 —— 这是最终回答
                messages.append({"role": "assistant", "content": msg.content})
                turn.finish(msg.content)
                return msg.content

            # 1) 先把"模型想调工具"这条 assistant 消息原样记进历史
            messages.append(_assistant_msg(msg))

            # 2) 逐个执行，结果以 role=tool 回填（必须带上对应的 tool_call_id）
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                t0 = time.perf_counter()
                result = run_tool(tc.function.name, args)
                turn.add_tool_call(tc.function.name, args, result,
                                   (time.perf_counter() - t0) * 1000)
                if on_tool:
                    on_tool(tc.function.name, args, result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            # 3) 带着工具结果再次进入循环，让模型继续（可能再调，或给最终答案）

        turn.finish("（工具调用次数过多，已停止）")
        return "（工具调用次数过多，已停止）"
    except Exception as e:
        turn.finish(None, error=str(e))
        raise


async def run_with_tools_async(aclient, model, messages, on_tool=None, session_id="-") -> str:
    """run_with_tools 的异步版（高并发用）。

    - 模型调用 await，不阻塞事件循环；多个请求的网络等待可真正重叠。
    - 工具函数本身是同步的（其中 search_knowledge 还会发 embedding 网络请求，属阻塞），
      用 asyncio.to_thread 卸载到线程池，避免在 async 端点里卡住整个事件循环。
    与同步版共享 TOOLS / DISPATCH / run_tool / 追踪逻辑。
    """
    turn = tracing.start_turn(session_id, messages[-1]["content"] if messages else "", model)
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = await aclient.chat.completions.create(
                model=model, messages=messages, tools=TOOLS, temperature=0.7,
            )
            turn.add_model_call(getattr(resp, "usage", None))
            msg = resp.choices[0].message

            if not msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content})
                turn.finish(msg.content)
                return msg.content

            messages.append(_assistant_msg(msg))
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                t0 = time.perf_counter()
                result = await asyncio.to_thread(run_tool, tc.function.name, args)
                turn.add_tool_call(tc.function.name, args, result,
                                   (time.perf_counter() - t0) * 1000)
                if on_tool:
                    on_tool(tc.function.name, args, result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        turn.finish("（工具调用次数过多，已停止）")
        return "（工具调用次数过多，已停止）"
    except Exception as e:
        turn.finish(None, error=str(e))
        raise
