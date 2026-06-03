"""结构化日志 / 追踪：把每轮对话与每次工具调用记成 JSON 行（JSONL）。

为什么要做：生产环境排查"为什么这轮答错了/为什么慢/花了多少 token"，靠 print 不行。
结构化 trace 让每轮请求可检索、可统计、可告警——这是可观测性的基础。

记录内容（每行一个 turn）：
  trace_id、时间、session、模型、用户输入、模型调用次数、token 用量、
  每次工具调用(名/参数/结果预览/耗时)、整轮延迟、最终回答或错误。

被 tools.run_with_tools 自动调用，无需手动埋点。
日志写到 logs/agent.jsonl；设环境变量 XZ_TRACE_ECHO=1 时同时打到 stderr。

查看摘要：
    python tracing.py          # 统计条数、平均延迟、token、工具使用分布
"""
import os
import sys
import json
import time
import uuid
import datetime
import threading

LOG_PATH = os.path.join(os.getenv("XZ_DATA_DIR", "."), "logs", "agent.jsonl")
_lock = threading.Lock()
ECHO = bool(os.getenv("XZ_TRACE_ECHO"))


class Turn:
    """一轮对话的追踪上下文。"""

    def __init__(self, session_id: str, user_input: str, model: str):
        self.rec = {
            "trace_id": uuid.uuid4().hex[:12],
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "model": model,
            "input": user_input,
            "model_calls": 0,
            "tokens": {"prompt": 0, "completion": 0, "total": 0},
            "tool_calls": [],
        }
        self._t0 = time.perf_counter()

    def add_model_call(self, usage) -> None:
        self.rec["model_calls"] += 1
        if usage:
            self.rec["tokens"]["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
            self.rec["tokens"]["completion"] += getattr(usage, "completion_tokens", 0) or 0
            self.rec["tokens"]["total"] += getattr(usage, "total_tokens", 0) or 0

    def add_tool_call(self, name: str, args: dict, result: str, ms: float) -> None:
        self.rec["tool_calls"].append({
            "name": name,
            "args": args,
            "result_preview": str(result)[:120],
            "ms": round(ms, 1),
        })

    def finish(self, answer, error: str = None) -> None:
        self.rec["latency_ms"] = round((time.perf_counter() - self._t0) * 1000, 1)
        self.rec["answer_preview"] = (str(answer)[:160] if answer else None)
        if error:
            self.rec["error"] = error
        _emit(self.rec)


def start_turn(session_id: str, user_input: str, model: str) -> Turn:
    return Turn(session_id, user_input, model)


def _emit(rec: dict) -> None:
    line = json.dumps(rec, ensure_ascii=False)
    with _lock:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    if ECHO:
        print(line, file=sys.stderr)


# ── 日志摘要（基础可观测性）────────────────────────────────
def _summary() -> None:
    if not os.path.exists(LOG_PATH):
        print(f"还没有日志：{LOG_PATH}")
        return
    n = 0
    lat = []
    toks = 0
    tool_hist: dict[str, int] = {}
    errors = 0
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            n += 1
            lat.append(r.get("latency_ms", 0))
            toks += r.get("tokens", {}).get("total", 0)
            if r.get("error"):
                errors += 1
            for tc in r.get("tool_calls", []):
                tool_hist[tc["name"]] = tool_hist.get(tc["name"], 0) + 1

    lat.sort()
    def pct(p):
        return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0
    print(f"日志文件：{LOG_PATH}")
    print(f"总轮数：{n}　错误：{errors}")
    print(f"延迟(ms)  平均={sum(lat)//max(1,len(lat))}  p50={pct(0.5)}  p95={pct(0.95)}  max={max(lat) if lat else 0}")
    print(f"总 token：{toks}　平均/轮：{toks//max(1,n)}")
    if tool_hist:
        print("工具使用分布：")
        for name, c in sorted(tool_hist.items(), key=lambda x: -x[1]):
            print(f"  {name:<18} {c}")


if __name__ == "__main__":
    try:                                   # Windows 控制台默认 GBK，强制 UTF-8 输出
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    _summary()
