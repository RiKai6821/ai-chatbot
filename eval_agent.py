"""Agent 评测：用例集 + 自动判分，衡量 Agent 是否"调对工具、答得准"。

为什么要做评测：
  改了 prompt / 模型 / 工具后，怎么知道有没有变差？靠人工试几句不可靠。
  评测把"期望行为"固化成用例，每次改动后一键回归，是 Agent 工程化的关键一环。

三类判分（可叠加）：
  1) 工具选择：实际调用的工具是否符合预期（该调的调了、该不调的没乱调）。
  2) 关键词断言：回答必须/禁止包含某些字符串（确定性、零成本）。
  3) LLM 裁判(可选)：用模型按 rubric 判断回答是否合格（开放型答案更鲁棒，需 --judge）。

用法：
    python eval_agent.py                 # 跑工具+关键词检查
    python eval_agent.py --judge         # 额外启用 LLM 裁判
    python eval_agent.py --verbose       # 打印每条的完整回答
退出码非 0 表示有用例失败，方便接入 CI。
"""
import os
import re
import sys
import json
import argparse

import config  # 加载 .env
import tools
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen-flash"
CASES_PATH = os.path.join("evals", "cases.json")


def run_case(case: dict):
    """跑一条用例，返回 (最终回答, 实际调用的工具名列表)。"""
    used = []
    msgs = [
        {"role": "system", "content": tools.AGENT_SYSTEM},
        {"role": "user", "content": case["input"]},
    ]
    answer = tools.run_with_tools(
        client, MODEL, msgs, on_tool=lambda n, a, r: used.append(n)
    )
    return answer, used


# ── 判分 ──────────────────────────────────────────────────
def check_tools(expected: list, used: list):
    eset, uset = set(expected), set(used)
    if not expected:
        ok = len(used) == 0
        return ok, f"期望不调工具，实际={used or '无'}"
    ok = eset.issubset(uset)
    return ok, f"期望{expected}，实际={used}"


def check_contains(answer: str, contains: list, not_contains: list):
    miss = [s for s in contains if s not in answer]
    bad = [s for s in not_contains if s in answer]
    return (not miss and not bad), f"缺少={miss or '—'} 误含={bad or '—'}"


def llm_judge(question: str, answer: str, rubric: str):
    prompt = (
        f"你是严格的评测裁判。判断下面的回答是否满足标准。\n"
        f"【问题】{question}\n【回答】{answer}\n【标准】{rubric}\n"
        f'只输出 JSON：{{"pass": true/false, "reason": "简短理由"}}'
    )
    resp = client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        obj = json.loads(text)
        return bool(obj.get("pass")), obj.get("reason", "")
    except json.JSONDecodeError:
        return False, f"裁判输出无法解析：{text[:60]}"


# ── 主流程 ────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", action="store_true", help="启用 LLM 裁判")
    ap.add_argument("--verbose", action="store_true", help="打印完整回答")
    args = ap.parse_args()

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    passed = 0
    tool_hits = 0
    print(f"运行 {len(cases)} 条用例（model={MODEL}{', +LLM裁判' if args.judge else ''}）\n")

    for c in cases:
        answer, used = run_case(c)
        tool_ok, tool_msg = check_tools(c.get("expect_tools", []), used)
        cont_ok, cont_msg = check_contains(
            answer, c.get("expect_contains", []), c.get("expect_not_contains", [])
        )
        judge_ok, judge_msg = True, ""
        if args.judge and c.get("judge"):
            judge_ok, judge_msg = llm_judge(c["input"], answer, c["judge"])

        ok = tool_ok and cont_ok and judge_ok
        passed += ok
        tool_hits += tool_ok
        mark = "✓" if ok else "✗"
        print(f"{mark} {c['name']:<20} 工具[{'OK' if tool_ok else 'X'}] "
              f"关键词[{'OK' if cont_ok else 'X'}]"
              f"{' 裁判[' + ('OK' if judge_ok else 'X') + ']' if args.judge and c.get('judge') else ''}")
        if not ok:
            if not tool_ok:  print(f"     工具: {tool_msg}")
            if not cont_ok:  print(f"     关键词: {cont_msg}")
            if not judge_ok: print(f"     裁判: {judge_msg}")
        if args.verbose:
            print(f"     回答: {answer}")

    n = len(cases)
    print(f"\n通过 {passed}/{n}（{passed*100//n}%）　工具选择正确 {tool_hits}/{n}")
    sys.exit(0 if passed == n else 1)


if __name__ == "__main__":
    main()
