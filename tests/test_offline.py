"""离线单元测试：纯逻辑、不联网、不花钱，适合每次 push 在 CI 跑。

覆盖：工具沙箱、会话持久化、RAG 切块/相似度、韧性的重试与超时。
（需要真实模型的端到端检查放在 eval_agent.py，由单独的、密钥门控的工作流跑。）
"""
import os
import asyncio

# 让 import config 的模块在无 .env 的 CI 里也能导入（仅占位，不发任何网络请求）。
os.environ.setdefault("DASHSCOPE_API_KEY", "ci-test-key")

import tools
import store
import rag
import resilience


# ── 工具 ──────────────────────────────────────────────────
def test_calculate_ok():
    assert tools.calculate("(23*19+7)/2") == "222.0"
    assert tools.calculate("2**10") == "1024"


def test_calculate_sandbox():
    # eval 沙箱应拦截内建/危险调用
    assert "失败" in tools.calculate("__import__('os').system('echo x')")


def test_run_tool_unknown():
    assert "未知工具" in tools.run_tool("nope", {})


# ── 会话持久化 ────────────────────────────────────────────
def test_store_roundtrip():
    store.init(":memory:")
    assert store.load("chat", "x") is None
    store.save("chat", "x", [{"role": "system", "content": "s"},
                             {"role": "user", "content": "记住我叫小明"}])
    got = store.load("chat", "x")
    assert got[1]["content"] == "记住我叫小明"


# ── RAG 离线部分 ──────────────────────────────────────────
def test_rag_split():
    chunks = rag._split_doc("第一段内容。\n\n第二段也有内容。")
    assert chunks == ["第一段内容。", "第二段也有内容。"]


def test_rag_cosine():
    assert abs(rag._cosine([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-6
    assert abs(rag._cosine([1, 0], [0, 1])) < 1e-6


# ── 韧性：重试 / 超时 ─────────────────────────────────────
def test_retry_then_succeed():
    class Tmp(Exception):
        pass
    old = resilience.RETRYABLE
    resilience.RETRYABLE = (Tmp,)
    resilience.RETRY_BASE = 0.001
    try:
        n = {"i": 0}

        async def flaky():
            n["i"] += 1
            if n["i"] < 3:
                raise Tmp()
            return "ok"

        assert asyncio.run(resilience.acall(lambda: flaky(), attempts=5)) == "ok"
        assert n["i"] == 3
    finally:
        resilience.RETRYABLE = old


def test_non_retryable_raises_immediately():
    class Fatal(Exception):
        pass
    n = {"i": 0}

    async def boom():
        n["i"] += 1
        raise Fatal()

    try:
        asyncio.run(resilience.acall(lambda: boom(), attempts=3))
        assert False, "应当抛出 Fatal"
    except Fatal:
        pass
    assert n["i"] == 1          # 未重试


def test_timeout_raises():
    async def slow():
        await asyncio.sleep(0.2)
        return "late"

    try:
        asyncio.run(resilience.acall(lambda: slow(), attempts=1, timeout=0.01))
        assert False, "应当超时"
    except asyncio.TimeoutError:
        pass
