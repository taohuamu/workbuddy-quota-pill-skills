# workbuddy-quota-pill-skills

把 [workbuddy-quota-pill](../workbuddy-quota-pill) 的数据层包装成一个 WorkBuddy 技能：在对话里问「还剩多少额度」，直接拿到各模型的周期配额表。

本目录与主项目分离，是因为两者交付对象不同——主项目交付一个常驻桌面程序，这里交付一个可被调用的技能。数据层共用同一份实现，见下文「同源约束」。

## 结构

```
workbuddy-quota-pill-skills/
├── quota-pill/                  # 技能本体，可直接放进 ~/.workbuddy/skills/
│   ├── SKILL.md                 # 路由 + 操作步骤 + 规则 + 坑 + 可选提醒（72 行）
│   ├── scripts/
│   │   ├── quota_watch.py       # 数据层，与主项目逐字节同源
│   │   ├── quota_report.py      # 输出层：Markdown 表格 + 签名缓存
│   │   ├── notify.py            # 阈值提醒：命中时发系统通知
│   │   ├── install_task.py      # 注册/注销提醒用的计划任务
│   │   └── sync_check.py        # 校验副本是否与主项目脱节
│   └── references/
│       ├── data-source.md       # 字段含义、覆盖率、模型清单（易变）
│       └── troubleshooting.md   # 排查顺序
└── tools/
    ├── install.py               # 装/卸到技能目录（默认建目录联接）
    ├── validate_skill.py        # frontmatter 与结构校验
    ├── test_output_contract.py  # 输出层契约测试（19 项）
    └── route_test.md            # 真路由测试清单（需新会话手工执行）
```

## 安装

```bash
python tools/install.py            # 默认建目录联接，改完即时生效
python tools/install.py --copy     # 复制一份，改完需重装
python tools/install.py --status
python tools/install.py --uninstall
```

安装后**新开一个会话**，问「现在还剩多少额度」，应出现 7 列表格。当前会话的技能清单在启动时已加载，装了也不会立刻生效。

## 真路由测试

`description` 决定技能何时被选中，而这条链路只能靠真的发一句话来验证——静态检查只能证明「问句里有能对上的词」，证明不了模型会选它。

步骤见 [`tools/route_test.md`](tools/route_test.md)：5 条正例、3 条反例、判定标准与三条失败分支（未加载 / 从不触发 / 触发报错）。两个要点：**必须新开会话**（技能清单在会话启动时加载），**一次只发一句**。

## 同源约束

`quota-pill/scripts/quota_watch.py` 是主项目 `quota_watch.py` 的**逐字节副本**，不是重新实现。原因是配额周期、stale 判定、置信度分档这些语义一旦有两份实现，就必然漂移——第一轮迭代里手写版本就因为漏掉「`reset_at` 是字符串」把整列算成了空。

主项目改了数据层，跑一次：

```bash
python quota-pill/scripts/sync_check.py        # 不一致时返回 1
python quota-pill/scripts/sync_check.py --fix  # 用上游覆盖副本
```

它还会顺带校验 `references/` 的「上次核对」日期是否落后于文件自身的修改时间——内容改了却忘改日期，读者会以为结论还停在旧日期。这一项只提醒，不阻断。

## 主动提醒（可选附件）

主打的是问答：你问一句，拿一张表。提醒是附加能力，**默认关闭**，只有用户明确要求时才装。

原因是它会在系统里留一个计划任务，卸载技能不会连带删掉；而且企业环境可能禁用任务计划程序。所以不做默认行为，也不主动推荐。

需要时：

```bash
python quota-pill/scripts/notify.py --dry-run              # 先看判定
python quota-pill/scripts/install_task.py --every 10       # 注册，每 10 分钟
python quota-pill/scripts/install_task.py --status
python quota-pill/scripts/install_task.py --uninstall
```

触发条件是 level 为 `critical` 或 `warn`，阈值与报告窗一致。同一模型同一等级 2 小时内不重复提醒，等级升级会再弹一次。状态记在 `%LOCALAPPDATA%\quota-pill\notify-state.json`。

**卸载要点**：`install.py --uninstall` 只删技能目录，计划任务要另行删除——

```
schtasks /Delete /TN "WorkBuddyQuotaPill-Notify" /F
```

`install.py --uninstall` 检测到开过提醒时会提示这一条。

## 测试

```bash
python tools/validate_skill.py quota-pill/SKILL.md
python tools/test_output_contract.py
```

校验器检查：`name` 与目录同名且符合命名规则、`description` ≤1024 字符、正文 ≤500 行、引用的 `references/` 存在、`scripts/` 内脚本语法可编译。

契约测试检查：表头完整、表体行数等于本周期模型数、每个模型的百分比与数据层一致、上一周期的模型不出现在表里、末行带取数耗时与日志目录、缓存与强制重扫、空日志目录不抛栈、副本与主项目同源。

## 已知限制

- 只支持 Windows 上装了 WorkBuddy 且跑过对话的机器——没有日志就没有数据。
- 需要本机有 Python 3.8+；`python` 不在 PATH 时技能会退回 `py`。
- 首次查询全量扫描日志，日志大的机器可能 1–3 秒；之后命中缓存约 0.1 秒。
- 技能的产出是文本表格，没有常驻窗口。想要「一直看得见」，用主项目的托盘版。
- 主动提醒靠计划任务，检查间隔即最大延迟：设 10 分钟，最坏情况是耗尽后 10 分钟才提醒。
