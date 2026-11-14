# 迭代状态

轮次：5 / 5（**已结束**）
技能路径：`D:\AI_work\WorkBuddy_work\2026-11-05-22-37-57\workbuddy-quota-pill-skills\quota-pill`
基线备份路径：`D:\AI_work\WorkBuddy_work\2026-11-05-22-37-57\workbuddy-quota-pill-skills\_iteration\backup_baseline_20261114_1947`
基线 SKILL.md 哈希：`1acd4c8ad69df2ae68c880629fc028a1d3e01b144c6be01508f65633a2a8f777`

## 已修 Bug 清单

- [B1] `metadata.requires.bins` 无任何消费方（asar 检索 0 命中），已删除。
- [B3] 提醒脚本增速窗口 15 分钟、报告 60 分钟，差异无文档说明，已补进 `scheduling.md`。
- [B4] 「主动提醒」节 20 行占正文 27%，属低频路径，已压缩到 11 行并下沉细节。
- [B5] 正文引用 `tools/install.py`，市场用户没有该目录，引用已删。
- [B6] 输出验收未覆盖 `quota_report.py` 的「注意：…存在触限风险」行，已补。
- [B7] `python` / `py` 都不存在时无指令，已补「如实说明缺少 Python，不要安装或改 PATH」。
- [B8] 覆盖率表数值滞后（deepseek 51% → 实测 56.6%），已更新。
- [B9] 多个模型的「极少」标注与实测不符（hy3 / kimi-k3-1 / kimi-k3.1-pro / glm-5.3），
  已改成「N 次调用中 M 次带」的确定表述。
- [B10] 缺 7 个有调用记录的模型（mimo-v2.6-pro、glm-5.2、space-bunny、minimax-m3.1-flash、
  kimi-k2.8-preview、fast-model、hy4free），已汇总登记。
- [B11] **核对方法失效（P1）**：教的命令只列「有 quota」的模型，永远发现不了「有调用无 quota」
  的新模型，而表里一半是这类。已拆成「报告口径 + 日志清点口径」两段并说明缘由。

## 待修 Bug 清单

- [B2] P2　版本号双写（顶层 `version` 与 `metadata.version`）。**需用户决策**：
  `tools/package.py` 的 `version()` 读 `metadata.version`，删任一处都要改技能目录外文件。

## 观察项与不做事项

- **不做**：把 `--json` 写进 SKILL.md——只服务契约测试，对模型是噪声。
- **不做**：给空数据补非 0 退出码——输出文本已说明，模型不依赖退出码。
- **不做**：`message_for()` 改用 `verdict`——会改变用户看到的通知文案，属对外行为变化。
- **观察**：`versions\current` 是记录版本号的文本文件而非目录，不能用作解释器兜底路径。

## 回归用例集

| 编号 | 预期 | 执行方式 | 当前 |
|---|---|---|---|
| T1 | 结构校验 PASS | `python tools/validate_skill.py quota-pill/SKILL.md` | 通过 |
| T2 | 输出层契约 19/19 | `python tools/test_output_contract.py` | 通过 |
| T3 | 与主项目同源且 references 日期不落后 | `python quota-pill/scripts/sync_check.py`（rc=0） | 通过 |
| T4 | 正常查询出 7 列表 | `quota_report.py --no-cache` | 通过 |
| T5 | `--json` 可解析且含 report.models | 同上加 `--json` | 通过 |
| T6 | 空日志目录降级不抛栈 | `WORKBUDDY_HOME=<空目录> --no-cache` | 通过 |
| T7 | 上一周期模型被过滤，末行报「另有 N 个」 | 契约断言 + R5 真会话末行 | 通过 |
| T8 | frontmatter 可被标准 YAML 解析 | PyYAML `safe_load` | 通过 |
| T9 | SKILL.md 引用的 references 均存在 | `validate_skill.py` 内含 | 通过 |
| T10–T14 | 触发层：5 正例命中、4 反例不误触发 | 真会话，见 `tools/route_test.md` 与 R5 | 通过 |

触发层用例不写入公开文档，只在本文件记结论。`description` 一旦改动必须重跑真路由。

## 上轮改动结果

- [C1] 删 `metadata.requires` → 保留
- [C2] `scheduling.md` 补窗口差异 → 保留
- [C3] `SKILL.md` 压缩提醒节 + `scheduling.md` 补卸载顺序 → 保留（正文 73 → 63）
- [C4] 「快速指导」补两条验收 → 保留（63 → 67，拆行所致）
- [C5] `data-source.md` 数值更新 + 核对方法补全 → 保留

## 连续无实质改进轮数

1（R5 无改动；因已达最大轮次 5 而终止，未累计到 2）

## 收敛判定

**迭代结束**（达到最大轮次）。详见 `总结报告.md`。

## 中断标记

无
