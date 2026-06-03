"""上游调用健壮性：并发限流 + 指数退避重试。

生产环境里大模型 API 会偶发限流(429)、超时、连接抖动、5xx。直接报错给用户体验差，
无脑重试又会雪上加霜。这里给出两道防线：
  1) 并发信号量：限制同时打到上游的请求数，平滑压力（避免自己把自己打限流）。
  2) 指数退避 + 抖动重试：对"可重试"错误退避后重试，抖动避免惊群同步重试。

配置（环境变量，均有默认值）：
  XZ_MAX_CONCURRENCY  同时在途的上游调用上限（默认 8）
  XZ_RETRY_ATTEMPTS   最大尝试次数（默认 3）
  XZ_RETRY_BASE       退避基数秒（默认 0.5）
  XZ_RETRY_CAP        单次退避上限秒（默认 8）
  XZ_TIMEOUT          单次上游调用超时秒（默认 30）——超时会被取消并按可重试处理
"""
import os
import random
import asyncio
import logging

from openai import (
    RateLimitError, APITimeoutError, APIConnectionError, InternalServerError,
)

log = logging.getLogger("resilience")

MAX_CONCURRENCY = int(os.getenv("XZ_MAX_CONCURRENCY", "8"))
RETRY_ATTEMPTS = int(os.getenv("XZ_RETRY_ATTEMPTS", "3"))
RETRY_BASE = float(os.getenv("XZ_RETRY_BASE", "0.5"))
RETRY_CAP = float(os.getenv("XZ_RETRY_CAP", "8.0"))
TIMEOUT = float(os.getenv("XZ_TIMEOUT", "30"))

# 哪些异常值得重试（瞬时/可恢复）。鉴权错误、参数错误等不在此列，不该重试。
RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)

# 信号量按事件循环懒创建：asyncio.Semaphore 绑定到首次使用它的事件循环，
# 跨循环复用会报错。按当前运行的 loop 缓存一份，兼容 uvicorn / 测试里多次 asyncio.run。
_sems: dict = {}


def _get_sem() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _sems.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        _sems[loop] = sem
    return sem


async def acall(make_coro, *, attempts: int = RETRY_ATTEMPTS, timeout: float = None):
    """在并发上限内执行 make_coro()（返回协程的工厂），带超时；可重试错误按指数退避+抖动重试。

    make_coro 必须是"零参、每次调用返回一个新协程"的工厂（因为协程不能重复 await）：
        await acall(lambda: client.chat.completions.create(...))
    超时(asyncio.TimeoutError)与瞬时错误一并按可重试处理；耗尽后抛出最后一次错误。
    """
    timeout = TIMEOUT if timeout is None else timeout
    last_err = None
    async with _get_sem():                 # 并发限流：超过上限的调用在此排队
        for i in range(attempts):
            try:
                # wait_for 给单次调用设硬超时；超时会取消该协程，避免慢请求拖死并发槽
                return await asyncio.wait_for(make_coro(), timeout)
            except (*RETRYABLE, asyncio.TimeoutError) as e:
                last_err = e
                if i == attempts - 1:
                    break
                # 指数退避 + 抖动：base*2^i，封顶 CAP，乘以 [0.5,1.5) 抖动
                delay = min(RETRY_CAP, RETRY_BASE * (2 ** i)) * (0.5 + random.random())
                log.warning("上游错误 %s，第 %d/%d 次，%.2fs 后重试",
                            type(e).__name__, i + 1, attempts, delay)
                await asyncio.sleep(delay)
    raise last_err
