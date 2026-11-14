---
name: quota-pill
description: 查询 WorkBuddy 各模型本周期（24 小时滚动窗口）的配额已用百分比、重置时刻、消耗增速与触限预测，也可开启阈值提醒（接近耗尽时弹系统通知）。当用户问额度、配额、限额还剩多少，问什么时候重置、还能撑多久、为什么数字不动、哪个模型快用完了，要一份用量摘要，或要求「快用完时提醒我」「开个额度提醒」时使用。只读本地会话日志，不联网、不登录、不改文件。
agent_created: true
version: 0.4.3
license: MIT, see LICENSE.txt
display_name: "配额胶囊"
display_name_en: "Quota Pill"
description_zh: "在对话里查 WorkBuddy 各模型的配额用量、重置时刻与触限预测；接近耗尽时可开系统提醒。只读本地会话日志，不联网、不登录。"
description_en: "Check per-model quota usage, reset time and burn-out forecast in chat; optional threshold alerts. Read-only local logs, no network, no login."
visibility: "public"
allowed-tools: Bash(python:*) Read
---

# 配额胶囊（技能版）

## 适用场景

- 问某个或全部模型的周期配额：已用多少、什么时候重置、还剩多少。
- 问按当前速度多久会触限，或「这个任务用哪个模型安全」。
- 问「数字为什么不动」「某个模型为什么不在列表里」。
- 要一份可复制走的 Markdown 用量摘要。
- 要求「快用完时提醒我」「开个额度提醒」：见下方「主动提醒」，属可选附件，需用户明确要求才启用。

## 不适用场景

- 账号积分余额、积分包到期：另一套计量，读 billing 接口，本技能不涉及。
- 统计 token 数、成本、缓存命中率：用其它用量看板技能。
- 要求安装、修改、清理、上传任何文件：本技能只读。

## 快速指导

1. 运行 `python "${CODEBUDDY_SKILL_DIR}/scripts/quota_report.py"`；若 `python` 不存在，改用 `py`。
   **必须用绝对路径**——工作目录不在技能目录下，相对路径必然找不到文件。两个都没有就如实
   说明本机缺少 Python，不要尝试安装或改 PATH。
2. 把输出的表格原样放进回答：不要重排行序，不要四舍五入改写数字，不要删掉末行的
   「取数耗时 / 日志目录」。若输出里还有「**注意**：…存在触限风险」一行，一并保留——
   那是唯一把风险顶到眼前的地方。
3. 表格后补一句结论：哪个模型最接近触限、预计还有多久；若某行显示「暂不预测」，照实说明样本不足，不要自己补算。
4. 需要解释字段或排查「为什么没有某个模型」时，读 `references/data-source.md`。

## 主动提醒（可选附件，默认关闭）

只有用户明确要求「快用完时提醒我」「开个额度提醒」时才启用；不要主动建议，也不要装完技能
就顺手装上——它会在系统里留一个计划任务。

1. 注册：`python "${CODEBUDDY_SKILL_DIR}/scripts/install_task.py" --every 10`，成功即完成。
   加 `--dry-run` 只打印将执行的命令；`--status` 查看；`--uninstall` 关闭。
2. 脚本自己选后端（`schtasks.exe` → PowerShell ScheduledTasks 模块 → 人工）。**只有**它打印
   「没有可用的调度后端」时才把命令交给用户，且**不要尝试绕过**（改注册表、换 shell、写启动项
   都不算解决），说明这是本机策略限制、不是脚本缺陷。想先看本机走哪条路：
   `python "${CODEBUDDY_SKILL_DIR}/scripts/probe_scheduler.py"`。
3. 触发条件二选一：任一模型已用达 80%，或预计 1 小时内触限（`--pct` / `--warn` 可调）。
   同一模型同一等级 2 小时内只提醒一次，等级变化会再弹。

副本机制、后端判定、错误码、卸载顺序见 `references/scheduling.md`。

## 高信号规则

- `percent` 是服务端下发的原值，粒度 1%。不得插值，不得改写成「约 X%」。
- 只有本周期用过、且服务端下发了 `quota` 的模型才在表里。缺模型不等于读取失败，不要补 0% 充数。
- `quota.model` 可能和 `providerData.model` 不同名（如 `hy4` / `hy4-free`），按前者展示。
- 停在上一周期的模型已被过滤，末行会说明「另有 N 个停在上一周期」。回答时不要把它们说成当前用量。
- 每行末尾的「数据新鲜度」必须保留：它是判断数字是否可信的唯一凭据。
- 扫描范围是本机全部历史会话（`projects/*/*.jsonl`），不是当前这一次对话。表里模型少，
  是这台机器本周期只用过这几家，不要说成「只统计到本轮会话」。
- 「预计触限」为「暂不预测」或可信度为「低」时，只说明样本不足。不要拿增速去反推
  「按这个速度会不会用完」——低可信度的增速就是噪声，推出来必然自相矛盾。

## 关键陷阱

- `reset_at` 是字符串形式的 Unix 秒（不是数字），直接做算术会报错或算出 1970 年。
- 全量扫描随日志增长变慢，脚本已带签名缓存；`--no-cache` 才是强制重扫。
- 跨年比较时间不要用字符串，统一用 epoch（脚本已处理）。
- 单条坏行只丢自己，不要让整次查询失败。

## 延伸阅读

- `references/data-source.md`：字段含义、字段覆盖率、模型清单与核对命令。
- `references/troubleshooting.md`：数字不动、模型缺失、目录找不到的排查顺序。
- `references/scheduling.md`：计划任务的后端选择、降级链、错误码与来源清单。
