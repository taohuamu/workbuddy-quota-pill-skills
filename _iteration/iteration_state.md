# 迭代状态（第二轮）

轮次：5 / 5（**已结束**）
技能路径：`D:\AI_work\WorkBuddy_work\2026-11-05-22-37-57\workbuddy-quota-pill-skills\quota-pill`
基线备份路径：`_iteration/backup_baseline_20261114_2103`（11 文件 / 100 KB）
基线 SKILL.md 哈希：`4ca6f0c51545777820be24e35dee918ef5b56461932492bbf8f674147b7d7b80`
结束版本：0.4.4
上一轮记录：`_iteration/round1/`（R1–R5 + 迭代后 C6–C9）

## 已修 Bug 清单

- [B1] P1　README 结构树补 `phrasing.py`；去掉会持续漂移的「73 行」。
- [B2] P1　`install_task.py` 支持 `--pct` / `--warn` 并写进任务动作；三条命令构造同步；
  实测 `Arguments` 与 `notify.log` 均显示自定义阈值。
- [B3] P2　删无用常量 `LEVEL_CN`（`LEVEL_RANK` 保留）。
- [B4] P3　注释「这两个模块」改为「同目录另外两个模块」。
- [B5] P1　SKILL.md 与 README 补「怎么改阈值」，含「改完必须重跑安装」。
- [B6] P2　README 副本说明补齐三个文件名。
- [B7] P2　`troubleshooting.md` 的相对路径命令改 `${CODEBUDDY_SKILL_DIR}`，与
  `data-source.md` 一致；照做不再报 `can't open file`。
- [B8] P2　`troubleshooting.md` 新增第 8 节「改了提醒阈值不生效」。
- [B9] P3　`scheduling.md` 补 `--pct` / `--warn` 的完整命令。
- [B10] P2　`how-it-works.md` 补 runtime 三个文件名与「阈值写进任务动作」的机制。
- [B11] P2　`SKILL.md` 不再逐字引用已不存在的「存在触限风险」，改为描述末行结构。
- [B12] P3　同上，「取数耗时」的说法与实际输出「取数 0.86 秒」对齐。

## 待修 Bug 清单

无。

## 观察项与不做事项

- **观察**：`phrasing.VERDICT_TEXT["重置前就会耗尽"]` 实际不可达（该 verdict 只在 `eta`
  非空时产生，必然走 `_within()`）。保留作防御，不删。
- **不做**：`--status` 显示任务当前阈值——需解析 Arguments 字符串；R1 改为安装时直接打印，
  且 `notify.log` 每行末尾都带，够用。
- **不做**：为凑轮次改写措辞。R5 台账为空即判定收敛。

## 回归用例集

| 编号 | 预期 | 执行方式 | 当前 |
|---|---|---|---|
| T1 | 结构校验 PASS | `tools/validate_skill.py` | 通过 |
| T2 | 输出层契约 19/19 | `tools/test_output_contract.py` | 通过 |
| T3 | 同源 + references 日期 | `quota-pill/scripts/sync_check.py` | 通过 |
| T4 | 7 列表 | `quota_report.py --no-cache` | 通过 |
| T5 | `--json` 可解析 | 同上加 `--json` | 通过 |
| T6 | 空目录降级 | `WORKBUDDY_HOME=<空目录>` | 通过 |
| T7 | 版本单源且为 0.4.4 | `grep -c metadata`=0；`package.version()` | 通过 |
| T8 | YAML 可解析 | PyYAML（需 3.14 解释器） | 通过 |
| T9 | references 均存在 | `validate_skill.py` | 通过 |
| T17 | README 结构树与 scripts/ 一致 | 提取树内 .py 与 glob 比对 | 通过 |
| T18 | 阈值出现在任务动作里 | `--dry-run` + 真注册后读 `Arguments` | 通过 |
| T19 | 无未使用的大写常量 | 逐文件正则统计 | 通过 |
| T20 | 文档里给出的命令可直接执行 | 抽查 `--pct/--warn` 那条 | 通过 |
| T21 | `troubleshooting` 的缓存验证命令可跑 | 同一命令连跑两次 | 通过（0.86s → 0.03s） |
| T22 | 文档声称会出现的输出串确实出现 | 实际输出 grep | 通过 |
| T10–T14 | 触发层 5 正例 / 4 反例 | 真会话 | 通过（R5 抽检 1/1、1/1，叠加历史 5/5、0/4） |

## 上轮改动结果

- [C1] README 结构树补文件、去行数 → 保留
- [C2] 删 `LEVEL_CN` → 保留
- [C3] `install_task` 阈值参数 → 保留（端到端实测）
- [C4] SKILL.md 补阈值用法 → 保留
- [C5] README 补命令示例与说明 → 保留
- [C6] README 副本三文件 → 保留
- [C7] troubleshooting 绝对路径 → 保留
- [C8] troubleshooting 第 8 节 → 保留
- [C9] scheduling 补命令 → 保留
- [C10] how-it-works 机制补全 → 保留
- [C11] SKILL.md 第 2 条改描述、去逐字引用 → 保留

## 连续无实质改进轮数

1（R5 无改动；因达到最大轮次 5 而终止，未累计到 2）

## 收敛判定

**迭代结束**（达到最大轮次）。详见 `_iteration/总结报告.md`。

## 中断标记

无
