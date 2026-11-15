# workbuddy-quota-pill-skills

[workbuddy-quota-pill](https://github.com/taohuamu/workbuddy-quota-pill) 的 WorkBuddy 技能版。安装后在对话里问「还剩多少额度」，可以直接拿到各模型本周期（24 小时窗口）的配额百分比、重置时刻，以及按最近 15 分钟消耗算出的到上限时间。

本仓库与主项目分开，是因为两者交付对象不同。主项目交付一个常驻桌面程序，这里交付一个可被调用的技能。不过数据层是同一份文件，具体请见下文「同源约束」。

## 结构

```
workbuddy-quota-pill-skills/
├── LICENSE                      # MIT
├── quota-pill/                  # 技能本体，可直接放进 ~/.workbuddy/skills/
│   ├── SKILL.md                 # 路由 + 操作步骤 + 规则 + 坑 + 可选提醒
│   ├── scripts/
│   │   ├── quota_watch.py       # 数据层，与主项目逐字节同源
│   │   ├── forecast.py          # 预测层：数涨幅 → χ² 判定 → Beta 分位给时间（同样同源）
│   │   ├── quota_report.py      # 输出层：Markdown 表格 + 签名缓存
│   │   ├── notify.py            # 阈值提醒：命中时发系统通知
│   │   ├── phrasing.py          # 一句话文案，报告与通知共用同一句
│   │   ├── install_task.py      # 注册/注销提醒用的计划任务（自动选后端）
│   │   ├── probe_scheduler.py   # 探测 schtasks / 定时任务模块是否可用
│   │   └── sync_check.py        # 校验 data/forecast 两个副本与 references 日期
│   └── references/
│       ├── data-source.md       # 字段含义、覆盖率、模型清单（易变）
│       ├── troubleshooting.md   # 排查顺序
│       └── scheduling.md        # 调度后端选路、错误码、已知限制
├── assets/
│   └── icon-512.png             # 市场图标（另出 256 / 128 供列表缩略）
├── tools/
│   ├── install.py               # 装/卸到技能目录（默认建目录联接）
│   ├── make_icon.py             # 生成三档尺寸的市场图标
│   ├── package.py               # 打 zip 分发物（含试装说明与哈希清单）
│   ├── validate_skill.py        # frontmatter 与结构校验
│   ├── test_output_contract.py  # 输出层契约测试（含退出码、列数、文档一致性）
│   ├── test_forecast.py         # 预测层行为测试（观测/判定/读数/文案）
│   └── route_test.md            # 真路由测试清单（需新会话手工执行）
└── docs/
    └── how-it-works.md          # 运行逻辑：链路、判定、缓存、失效模式
```

具体的分层原因和经历请见 [`docs/how-it-works.md`](docs/how-it-works.md)。

## 安装

```bash
python tools/install.py            # 默认建目录联接，改完即时生效
python tools/install.py --copy     # 复制一份，改完需重装
python tools/install.py --status
python tools/install.py --uninstall
```

安装后**新开一个会话**，问「现在还剩多少额度」，应出现 6 列表格（模型 / 已用 / 本周期重置 / 近 15 分钟 / 按此速度 / 数据新鲜度）。当前会话的技能清单在启动时已加载，装了也不会立刻生效。

## 发给别人试

```bash
python tools/package.py             # 版本号取自 SKILL.md，包名带当天日期
python tools/package.py --tag test2
```

包里有 `START-HERE.txt`，写的是在另一台机器上怎么装：解压、`python tools\install.py --copy`、新开会话。用 `--copy` 而不是默认的目录联接，是因为解压目录往往是一次性的，联接会指着它不放。

打包前先跑技能结构校验和输出层契约测试，任一项不过就不出包——一个装不上的包比没有包更糟，对方只会怀疑是自己的环境问题。出包后重新打开 zip 复核：文件齐全、没混进字节码、关键文件哈希与源文件一致。同目录另有 `MANIFEST.txt`，拷贝过程中被改动或截断时能对出来。

白名单只放 `quota-pill/`、`docs/`、`README.md`、`LICENSE` 和 `tools/install.py`。`route_test.md`、三个测试脚本和 `.git` 对收包的人没有用，只会让包里多出几个不知该点哪个的文件。许可证必须跟着走，这条不能省。

`dist/` 在 `.gitignore` 里，不进仓库。

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

单独克隆本仓库时旁边没有主项目，`sync_check.py` 会退出 2 并打印「找不到上游文件」。这是正常现象，不是安装问题；要对比就手动指过去：`--upstream <主项目>/quota_watch.py`。

## 主动提醒（可选附件）

主打的是问答：你问一句，拿一张表。提醒是附加能力，**默认关闭**，只有用户明确要求时才装。

原因是它会在系统里留一个计划任务，而且企业环境可能禁用任务计划程序。所以不做默认行为，也不主动推荐。

需要时：

```bash
python quota-pill/scripts/probe_scheduler.py               # 先看本机哪条路可用
python quota-pill/scripts/notify.py --dry-run              # 再看判定
python quota-pill/scripts/install_task.py --every 10       # 注册，每 10 分钟
python quota-pill/scripts/install_task.py --every 10 --pct 70 --warn 3 --floor 60   # 同上，并改阈值
python quota-pill/scripts/install_task.py --status
python quota-pill/scripts/install_task.py --uninstall
```

阈值默认是「已用 ≥80%，或按当前速度 2 小时内会到上限（且已用已过 55%）」。
`--pct` / `--warn` / `--floor` 会写进任务动作，所以改完要重跑一次
安装。`--status` 会打出**安装时的间隔与阈值**（存在 `%LOCALAPPDATA%\quota-pill\install.json`），
它记的是安装那一刻；任务实际用过的值看 `notify.log` 每行末尾。

**注册会自动选后端**：先试 `schtasks.exe`，它被安全策略拦死（进程起不来）时改用系统自带的
ScheduledTasks 模块（经 powershell 调用），两者都不可用才把命令交给你手动执行。
`--backend powershell` 可强制指定。判定依据与错误码对照见 `quota-pill/references/scheduling.md`。

安装时会把 `notify.py`、`quota_watch.py`、`phrasing.py`、`forecast.py` 四个文件复制到
`%LOCALAPPDATA%\quota-pill\runtime\`，任务指向这份副本，
所以删掉、移动、重装技能都不会让任务指向空路径；改了脚本要重跑一次安装，`--status` 会提示副本落后。
`--dry-run` 只打印将执行的命令，不建目录也不注册任务。

触发条件二选一：任一模型已用达 80%，或按当前速度 2 小时内会到上限（`--pct` / `--warn` 可调，且要求已用过 `--floor`）；通知内容包含触发的模型以及所有 `critical` 的，正文只给结果（「按此速度约 40 分钟后到上限」/「近 15 分钟无新增」）。同一模型同一等级 2 小时内不重复提醒，等级变化会再弹一次。状态记在 `%LOCALAPPDATA%\quota-pill\notify-state.json`。

**卸载**：`install.py --uninstall` 会先删计划任务，再删技能目录。顺序是刻意的——反过来，两次操作之间
若正好到点，任务会去拉一个已经不存在的脚本。删之前先 `/Query` 一次，任务本就不存在时按「没有」处理，
不报错。

删除同样会自动选后端。只有在两条路都不可用时，脚本才会打印手动命令，执行一次即可：

```
schtasks /Delete /TN "WorkBuddyQuotaPill-Notify" /F
```

## 测试

```bash
python tools/validate_skill.py quota-pill/SKILL.md
python tools/test_output_contract.py
```

校验器检查：`name` 与目录同名且符合命名规则、`description` ≤1024 字符、正文 ≤500 行、引用的 `references/` 存在、`scripts/` 内脚本语法可编译。

契约测试检查：表头完整、表体行数等于本周期模型数、每个模型的百分比与数据层一致、上一周期的模型不出现在表里、末行带取数耗时与日志目录、缓存与强制重扫、空日志目录不抛栈、副本与主项目同源。

## 已知限制

- 只支持 Windows 上装了 WorkBuddy 且跑过对话的机器——没有日志就没有数据。
- 需要 Python 3.8+，但**不用另外装**：WorkBuddy 自带一份并已排进 PATH
  （`%USERPROFILE%\.workbuddy\binaries\python\versions\` 下，指向安装目录的 `resources\vendor\python`）。
  两台机器实测 `python --version` 拿到的都是这一份。`python` 找不到时退回 `py`。
- 首次查询全量扫描日志，日志大的机器可能 1–3 秒；之后命中缓存约 0.1 秒。
- 技能的产出是文本表格，没有常驻窗口。想要「一直看得见」，用主项目的托盘版。
- 主动提醒靠计划任务，检查间隔即最大延迟：设 10 分钟，最坏情况是耗尽后 10 分钟才提醒。

## 许可

MIT，见 [LICENSE](LICENSE)。

这是第三方工具，不是腾讯或 WorkBuddy 官方产物。它读的是本机会话日志里的字段，
字段含义与下发策略由客户端决定，可能随版本变化；数字对不上时先怀疑这个，
不必怀疑安装。
