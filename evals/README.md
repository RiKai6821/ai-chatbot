# Agent 评测

衡量 Agent 是否"**调对工具、答得准**"。改了 prompt / 模型 / 工具后一键回归，避免靠人工试几句。

## 运行

```bash
python eval_agent.py            # 工具选择 + 关键词断言（确定性、零额外成本）
python eval_agent.py --judge    # 额外启用 LLM 裁判（开放型答案更鲁棒）
python eval_agent.py --verbose  # 打印每条完整回答
```
退出码非 0 表示有用例失败，可直接接入 CI。

## 用例格式（`cases.json`）

```json
{
  "name": "wifi-5ghz",
  "input": "小智支持5GHz的wifi吗？",
  "expect_tools": ["search_knowledge"],   // 期望调用的工具（空数组=不该调任何工具）
  "expect_contains": ["2.4"],             // 回答必须包含
  "expect_not_contains": [],              // 回答禁止包含
  "judge": "回答应明确说明只支持2.4GHz"     // 可选：给 LLM 裁判的评判标准
}
```

## 三类判分

| 判分 | 说明 | 成本 |
|------|------|------|
| 工具选择 | 实际调用的工具是否符合 `expect_tools`（该调的调了、该不调没乱调） | 低 |
| 关键词断言 | `expect_contains` / `expect_not_contains` 子串检查 | 零 |
| LLM 裁判 | 用模型按 `judge` rubric 判断回答是否合格（`--judge` 开启） | 每条一次模型调用 |

## 经验教训（评测自身也要可靠）

- **关键词断言易脆**：曾用 `expect_not_contains:["支持5GHz"]`，但正确回答"不**支持5GHz**"恰好含该子串 → 误判。
  子串断言要避开这种包含关系，开放语义交给 LLM 裁判。
- **LLM 裁判有局限**：模型不知真实时钟，会把工具返回的真实日期当成"虚构"而判负。
  裁判 rubric 应聚焦"可从文本判断"的点（如"是否给出了具体时间"），而非它无从核实的事实。
