# 计划任务：后端选择与已知限制

上次核对：2026-11-14（本轮有实测，见文末「验证状态」）

提醒用的是 Windows 计划任务：每 N 分钟拉起一次 `notify.py`，跑完即退。本文记录
「用哪个后端注册」的判断依据，以及各后端在本项目里踩到的限制。

## 为什么需要两条路

`schtasks.exe` 在部分环境里会被安全策略列为禁止启动的程序：进程根本起不来，
Python 侧只看到 `OSError`（`PermissionError`，`winerror` 5），耗时约 1 ms。
这不是权限不足，也不是文件 ACL 问题——`schtasks.exe` 本身没有异常的 Deny 项，
是进程创建被拦在了更前面一层。

同一条策略不拦 PowerShell 的 `ScheduledTasks` 模块（它走 CIM 调用，不经过
`schtasks.exe`），所以在被拦的机器上仍然能注册、查询、删除任务。
这是本技能准备两条后端的原因。

## 选路顺序

```
probe_scheduler.py --json
   ├─ schtasks == ok           → 用 schtasks（命令最简单，兼容性最好）
   ├─ schtasks == blocked/error
   │    └─ scheduledtasks == ok → 用 PowerShell ScheduledTasks 模块
   └─ 两者都不可用              → 打印两条手动命令，交给用户
```

`install_task.py` 每次运行都会先探测，不需要用户选。`--backend powershell` 可强制指定，
用于排查「到底哪条路坏了」。

## 两条路的命令对照

| 动作 | schtasks | PowerShell |
|---|---|---|
| 注册 | `schtasks /Create /TN <名> /TR "<exe> <脚本>" /SC MINUTE /MO 10 /IT /F` | `New-ScheduledTaskAction` + `New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10)` + `Register-ScheduledTask -Force` |
| 查询 | `/Query /TN <名> /FO LIST` | `Get-ScheduledTask` / `Get-ScheduledTaskInfo` |
| 删除 | `/Delete /TN <名> /F` | `Unregister-ScheduledTask -Confirm:$false` |
| 立即运行 | `/Run /TN <名>` | `Start-ScheduledTask` |

## 能力差异（决定实现细节）

| 能力 | schtasks | PowerShell |
|---|---|---|
| 设置工作目录 | **无此参数**（官方参考的参数表里没有，只能靠 `/xml` 导入） | `New-ScheduledTaskAction -WorkingDirectory` |
| 含空格 / 中文路径 | 靠多层引号，`/TR` 整串要再包一层 | `-Argument` 与 `-WorkingDirectory` 分开传，不经 shell 切词 |
| 每 N 分钟重复 | `/SC MINUTE /MO N` | `-RepetitionInterval`，`Duration` 留空即无限 |
| 报错可读性 | 文本提示，本地化，解析靠关键词 | 抛异常，可取 `$_.Exception.Message` |
| 退出码 | 查不到任务返回 1，与「执行失败」同为 1 | 查不到返回 0 + 空结果，语义清楚 |
| 被策略拦截时的表现 | 进程起不来（`OSError`） | 通常不受影响 |

## 运行副本

任务动作指向 `%LOCALAPPDATA%\quota-pill\runtime\notify.py`，而不是技能目录里的脚本。
安装时复制 `notify.py` 与 `quota_watch.py` 两份过去，卸载时一并删除。

理由：任务是个长期存在的东西，技能目录却可能被删、被移动、被重装。指向技能目录时，
用户手动删一次目录就会留下一条每 10 分钟去拉空路径的任务——静默失败，也没有痕迹。

代价与对策：

| 代价 | 对策 |
|---|---|
| 改了 `notify.py` 不重装就不生效 | `--status` 比对文件大小，落后时提示「重跑一次安装」 |
| 多占一份磁盘 | 两份纯 Python，约 23 KB |

## 错误码对照（`LastTaskResult`）

注册成功不等于任务能跑。查 `Get-ScheduledTaskInfo` 或 `schtasks /Query /V` 的
`Last Result` 字段：

| 值 | 常量 | 含义 | 处置 |
|---|---|---|---|
| `0x0` | — | 成功 | — |
| `0x41301` | `SCHED_S_TASK_RUNNING` | 正在运行 | 稍后再查 |
| `0x41303` | `SCHED_S_TASK_HAS_NOT_RUN` | **从未运行过**，不是错误 | 刚注册的正常状态；若长期如此，查触发器 |
| `0x41306` | `SCHED_S_TASK_TERMINATED` | 被用户终止 | 检查是否手动结束 |
| `0x41307` | `SCHED_S_TASK_NO_VALID_TRIGGERS` | 没有有效触发器 | 触发器参数写错 |
| `0x8004130F` | `SCHED_E_ACCOUNT_INFORMATION_NOT_SET` | 账户信息缺失 | 指定 `-User` 或改用交互式登录类型 |
| `0x80041320` | `SCHED_E_USER_NOT_LOGGED_ON` | 用户未登录 | 用 `/IT` 或改为「不管用户是否登录」 |
| `0x80070005` | `E_ACCESSDENIED` | 拒绝访问 | 多为需要提权（如 `RunLevel Highest`） |

常被误读的是 `0x41303`：它是「还没跑过」，属于成功类常量，不是失败。

## 已知限制

- **提权需要管理员**：`-RunLevel Highest` 在非管理员会话下直接报「拒绝访问」；
  枚举值是 `Limited` / `Highest`，没有 `HighestAvailable`（那是另一个 API 的写法）。
  本项目不需要提权，`Limited` 即可。
- **只在该用户登录时运行**：任务以交互式令牌运行（对应 `/IT`），换用户或未登录时不触发。
- **调用 PowerShell 有固定开销**：空转约 0.35–0.4 秒，注册一次约 1.2 秒。相对 10 分钟的
  间隔可以忽略，但不适合放进每次对话的主路径。
- **控制台输出是 GBK**：中文 Windows 上从 Python 读 PowerShell 的 stderr，按 UTF-8 解会
  得到乱码。脚本统一按 GBK 解；需要可靠的 UTF-8 时在 PowerShell 里先设
  `[Console]::OutputEncoding=[Text.Encoding]::UTF8`。
- **只在本机验证过**：另一条路（另一台机器、另一套策略）的实际表现可能不同，
  所以保留探测而不是写死。
- **任务跑的是副本，不是技能目录**：安装时会把 `notify.py` 与 `quota_watch.py` 复制到
  `%LOCALAPPDATA%\quota-pill\runtime\`，任务动作指向副本。好处是删掉、移动、重装技能都不会
  让任务指向空路径；代价是改了脚本要重跑一次安装，`--status` 会提示副本落后。
  卸载时任务与副本一起删除。
- **解释器路径写死在任务动作里**：取的是安装时 `sys.executable` 同目录的 `pythonw.exe`。
  WorkBuddy 自带的 Python 路径带版本号（`…\binaries\python\versions\3.13.12\`），
  升级客户端或换 Python 之后这条路径就没了，任务每次启动都失败且**不会主动告诉你**。
  `--status` 里 `LastTaskResult` 会变成 `0x2`（系统找不到指定的文件），看到它就重跑一次安装。
  这条在换机、换版本后最容易踩，因为任务是静默的。

## 不采用的方案

- **`/XML` 导入**：仍然要经 `schtasks.exe`，被拦时同样起不来；且要自己拼 XML。
- **Task Scheduler COM（`ITaskService`）**：能力最全，但要 `comtypes` 之类的依赖，
  与本项目「无第三方依赖」的定位冲突，只在 PowerShell 也不可用时才值得考虑。
- **启动文件夹（Startup）**：只在登录时触发，做不到「每 10 分钟」。
- **常驻轮询进程**：效果等价于托盘版，但会留下一个长期进程，与「不常驻」的定位相反。

## 平台自带的定时任务

WorkBuddy 自身有「定时任务」，可以完全不用系统计划任务。但它有三条硬限制，与本场景
不匹配，故未采用：

1. 最小间隔 1 小时（分钟级被拒绝），配额可能在半小时内耗尽；
2. 每次触发是一轮完整对话，会消耗积分；
3. 本机任务需要客户端在运行，客户端退出即不执行。

## 验证状态

2026-11-14 在本机（Windows，非管理员）实测：

| 项 | 结果 |
|---|---|
| `schtasks` 调用 | 被拦，`OSError` / `WinError 5`，进程未启动 |
| PowerShell 注册 + 查询 + 删除 | 通过 |
| 任务真跑（`LastTaskResult`） | `0x0`，`notify.log` 有新记录 |
| 含空格与中文路径 | 通过，工作目录正确 |
| 每 10 分钟重复 | 通过，`Repetition Interval = PT10M` |
| `-RunLevel Highest`（非管理员） | 失败，「拒绝访问」 |
| 强制 `--backend schtasks` | 失败后自动降级到 PowerShell，成功 |
| 运行副本 | 通过：动作指向 `…\quota-pill\runtime\notify.py`，执行结果 `0x0`，日志有新行 |
| 卸载连带清副本 | 通过：任务 `CLEAN`，runtime 目录已消失 |
| `--dry-run` | 通过：只打印命令与目标路径，未建目录、未注册任务 |
| 副本落后提示 | 通过：人为截断副本后 `--status` 提示「重跑一次安装」 |
| 未运行状态的显示 | 通过：`LAST=从未运行`、`RESULT=0x41303（从未运行过，正常）` |

未验证：企业组策略同时禁用任务计划程序与 PowerShell 的情形；PowerShell 被降级到
受限语言模式（Constrained Language Mode）时的表现。

## 来源

- S1 WorkBuddy 定时任务官方文档（直接依据）
- S2 Microsoft `schtasks create` 参考（直接依据，确认无工作目录参数）
- S3 Microsoft `New-ScheduledTaskAction`（直接依据，`-WorkingDirectory` 与「默认在 system32 运行」）
- S4 Microsoft Task Scheduler 错误与成功常量（直接依据，`0x41303` 等）
- S5 `taracodlabs/aiden` 的 `skills/taskscheduler/SKILL.md`（可迁移依据，全程用 PowerShell 管任务）
- S6 `jshchnz/claude-code-scheduler` 的 `skills/scheduler/SKILL.md` 与 `PLATFORM_SETUP.md`
  （可迁移依据，Windows 段用 schtasks，并记录「PATH / 工作目录 / 引号」三类失败）
