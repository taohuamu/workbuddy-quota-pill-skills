"""注册 / 注销「配额阈值提醒」的 Windows 计划任务。

提醒脚本不常驻：计划任务每 N 分钟拉起一次，跑完立即退出。

调度后端按可用性自动选路（见 probe_scheduler.py）：
    schtasks.exe  → 首选，命令最轻；被安全策略拦截时进程根本起不来
    PowerShell    → 备选，走 CIM 调 ScheduledTasks 模块，不受同一条黑名单影响
    manual        → 两者都不可用，打印命令交给用户手动执行

    python install_task.py            # 安装（默认每 10 分钟）
    python install_task.py --every 5   # 改间隔
    python install_task.py --status    # 查看
    python install_task.py --uninstall # 卸载
    python install_task.py --backend powershell   # 指定后端，跳过探测
"""

import argparse
import os
import shutil
import subprocess
import sys

TASK_NAME = "WorkBuddyQuotaPill-Notify"
HERE = os.path.dirname(os.path.abspath(__file__))
NOTIFY = os.path.join(HERE, "notify.py")

STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "quota-pill")
# 任务动作指向这份副本，而不是技能目录：技能被删、被移动、被重装都不影响已注册的任务。
RUNTIME_DIR = os.path.join(STATE_DIR, "runtime")
# 任务跑的是这里的副本，不是技能目录。notify.py 依赖这两个模块，漏一个就能
# 直接 ImportError——而且任务失败是静默的，只有 --status 的 LastTaskResult 会变。
STAGE_FILES = ("notify.py", "quota_watch.py", "phrasing.py")

sys.path.insert(0, HERE)
try:
    import probe_scheduler as probe            # noqa: E402
except Exception:                              # noqa: BLE001
    probe = None


def python_for_task():
    """优先用 pythonw.exe，计划任务拉起时不会闪黑框。"""
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def stage_runtime():
    """把提醒脚本与数据层复制到 %LOCALAPPDATA%\\quota-pill\\runtime\\。

    任务动作必须指向一个「不随技能目录存亡」的路径：指向技能目录时，用户手动删掉
    技能会留下一条每 N 分钟去拉空路径的任务，静默失败且没有痕迹。
    """
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    for name in STAGE_FILES:
        src = os.path.join(HERE, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(RUNTIME_DIR, name))
    return os.path.join(RUNTIME_DIR, "notify.py")


def staged_is_stale():
    """runtime 里的副本是否落后于技能目录（改了代码没重装）。"""
    for name in STAGE_FILES:
        src = os.path.join(HERE, name)
        dst = os.path.join(RUNTIME_DIR, name)
        if not os.path.exists(dst):
            return True
        if os.path.exists(src) and os.path.getsize(src) != os.path.getsize(dst):
            return True
    return False


def run(args):
    """schtasks 可能被安全策略直接拦死（进程起不来），此时不要抛栈，
    退化成「返回失败」让调用方打印手动命令。"""
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _ps(script):
    """跑一段 PowerShell，返回 (returncode, stdout, stderr)。编码按 GBK 解。"""
    rc, out, err = probe._powershell(script) if probe else (None, "", "probe 缺失")
    if rc is None:
        return 1, "", err
    return rc, out, err


def _q(text):
    """PowerShell 单引号字面量：内部单引号写两遍。"""
    return "'" + str(text).replace("'", "''") + "'"


def backend(forced=None):
    if forced in ("schtasks", "powershell", "manual"):
        return forced
    if probe is None:
        return "schtasks"
    try:
        return probe.probe().get("recommended", "schtasks")
    except Exception:                          # noqa: BLE001
        return "schtasks"


# ---------------------------------------------------------------- 各后端实现

def _install_ps(every, target):
    script = (
        "$ErrorActionPreference='Stop'\n"
        "try {\n"
        "  $act = New-ScheduledTaskAction -Execute %s -Argument %s -WorkingDirectory %s\n"
        "  $trg = New-ScheduledTaskTrigger -Once -At (Get-Date) "
        "-RepetitionInterval (New-TimeSpan -Minutes %d)\n"
        "  $set = New-ScheduledTaskSettingsSet -StartWhenAvailable "
        "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit (New-TimeSpan -Minutes 3)\n"
        "  Register-ScheduledTask -TaskName %s -Action $act -Trigger $trg "
        "-Settings $set -Force | Out-Null\n"
        "  'OK'\n"
        "} catch { 'ERR: ' + $_.Exception.Message }\n"
    ) % (_q(python_for_task()), _q('"%s"' % target), _q(RUNTIME_DIR), every, _q(TASK_NAME))
    rc, out, err = _ps(script)
    return rc == 0 and out.strip().startswith("OK"), (out or err).strip()


def _install_schtasks(every, target):
    # /TR 的整串要再包一层引号，内部两个路径各自转义，否则 schtasks 只认第一个路径。
    tr = '"\\"%s\\" \\"%s\\""' % (python_for_task(), target)
    r = run(["schtasks", "/Create", "/TN", TASK_NAME, "/TR", tr,
             "/SC", "MINUTE", "/MO", str(every), "/IT", "/F"])
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def _status_ps():
    script = (
        "$t = Get-ScheduledTask -TaskName %s -ErrorAction SilentlyContinue\n"
        "if (-not $t) { 'ABSENT'; exit 0 }\n"
        "$i = Get-ScheduledTaskInfo -TaskName %s\n"
        "'STATE=' + $t.State\n"
        "'NEXT=' + $i.NextRunTime\n"
        "if ($i.LastRunTime.Year -lt 2000) { 'LAST=从未运行' } else { 'LAST=' + $i.LastRunTime }\n"
        "if ($i.LastTaskResult -eq 0x41303) { 'RESULT=0x41303（从未运行过，正常）' } "
        "else { 'RESULT=0x{0:X}' -f $i.LastTaskResult }\n"
    ) % (_q(TASK_NAME), _q(TASK_NAME))
    rc, out, err = _ps(script)
    return out.strip(), rc


def _uninstall_ps():
    script = (
        "$t = Get-ScheduledTask -TaskName %s -ErrorAction SilentlyContinue\n"
        "if (-not $t) { 'ABSENT'; exit 0 }\n"
        "try { Unregister-ScheduledTask -TaskName %s -Confirm:$false; 'DELETED' }\n"
        "catch { 'ERR: ' + $_.Exception.Message }\n"
    ) % (_q(TASK_NAME), _q(TASK_NAME))
    rc, out, err = _ps(script)
    return out.strip(), rc


def _manual_commands(every, target):
    lines = ["在命令提示符里手动执行（不需要管理员）：",
             'schtasks /Create /TN "%s" /TR "\\"%s\\" \\"%s\\"" /SC MINUTE /MO %d /IT /F'
             % (TASK_NAME, python_for_task(), target, every),
             "",
             "或在 PowerShell 里执行：",
             "$act = New-ScheduledTaskAction -Execute '%s' -Argument '\"%s\"' -WorkingDirectory '%s'"
             % (python_for_task(), target, RUNTIME_DIR),
             "$trg = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes %d)" % every,
             "Register-ScheduledTask -TaskName '%s' -Action $act -Trigger $trg -Force" % TASK_NAME]
    return lines


# ---------------------------------------------------------------- 对外命令

def status():
    be = backend()
    if be == "powershell":
        out, rc = _status_ps()
        if "ABSENT" in out:
            print("未安装")
            return 1
        for line in out.splitlines():
            print("  " + line)
    else:
        r = run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"])
        if r.returncode != 0:
            print("未安装")
            return 1
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith(("TaskName", "任务名", "Status", "状态",
                                "Next Run", "下次运行", "Task To Run", "要运行的任务")):
                print("  " + line)
    print("\n提醒脚本:", os.path.join(RUNTIME_DIR, "notify.py"))
    print("解释器  :", python_for_task())
    if staged_is_stale():
        print("提示    : runtime 副本落后于技能目录，重跑一次安装可更新")
    return 0


def install(every, forced=None, dry_run=False):
    if not os.path.exists(NOTIFY):
        print("找不到提醒脚本:", NOTIFY)
        return 1
    be = backend(forced)
    target = os.path.join(RUNTIME_DIR, "notify.py")

    if dry_run:
        print("后端      : %s" % be)
        print("副本目录  : %s" % RUNTIME_DIR)
        print("任务动作  : \"%s\" \"%s\"" % (python_for_task(), target))
        print("间隔      : %d 分钟" % every)
        print("\n将执行的命令：")
        for line in _manual_commands(every, target):
            print(line)
        return 0

    if be == "manual":
        print("没有可用的调度后端（schtasks 起不来，PowerShell 也不可用）。")
        for line in _manual_commands(every, target):
            print(line)
        return 1

    target = stage_runtime()
    ok, detail = _install_ps(every, target) if be == "powershell" else _install_schtasks(every, target)
    if not ok:
        print("安装失败（%s）：%s" % (be, detail))
        # schtasks 失败时自动再试一次 PowerShell —— 这是最常见的一种环境差异。
        if be == "schtasks" and backend() == "powershell":
            print("改用 PowerShell 重试…")
            ok, detail = _install_ps(every, target)
            be = "powershell"
    if not ok:
        print("安装失败（%s）：%s" % (be, detail))
        for line in _manual_commands(every, target):
            print(line)
        return 1

    print("已安装：每 %d 分钟检查一次，仅在当前用户登录时运行（后端 %s）" % (every, be))
    status()
    return 0


def task_exists():
    """True / False / None（判不了，通常是两个后端都不可用）。"""
    if backend() == "powershell":
        out, _ = _status_ps()
        if "ABSENT" in out:
            return False
        return True if "STATE=" in out else None
    r = run(["schtasks", "/Query", "/TN", TASK_NAME])
    if r.returncode == 0:
        return True
    # schtasks 起不来时 run() 也是返回 1，只能靠异常文本区分「进程没起来」与「任务不存在」。
    err = r.stderr or ""
    if "WinError" in err or "拒绝访问" in err:
        return None
    return False


def remove_task():
    """删除任务。返回 'deleted' / 'absent' / 'blocked' / 'failed'。"""
    exists = task_exists()
    if exists is False:
        return "absent"
    if exists is None:
        return "blocked"
    if backend() == "powershell":
        out, _ = _uninstall_ps()
        if out.startswith("DELETED"):
            return "deleted"
        return "absent" if "ABSENT" in out else "failed"
    r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    return "deleted" if r.returncode == 0 else "failed"


def cleanup_runtime():
    """删掉 runtime 副本。任务还在跑时不要调用：那会让它指向空路径。"""
    if os.path.isdir(RUNTIME_DIR):
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)


def uninstall():
    state = remove_task()
    if state in ("deleted", "absent"):
        # 任务已经不存在了，副本留着只会让下次装到旧版本。
        cleanup_runtime()
    if state == "absent":
        print("计划任务本来就不存在")
        return 0
    if state == "deleted":
        print("已卸载计划任务")
        return 0
    if state == "blocked":
        print("判不了任务是否存在（schtasks 起不来，PowerShell 也不可用）。可手动执行：")
    else:
        print("卸载失败。可手动执行：")
    print('  schtasks /Delete /TN "%s" /F' % TASK_NAME)
    print('  或：Unregister-ScheduledTask -TaskName "%s" -Confirm:$false' % TASK_NAME)
    return 1


def main():
    ap = argparse.ArgumentParser(description="配额提醒计划任务")
    ap.add_argument("--every", type=int, default=10, help="检查间隔（分钟）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令，不注册任务")
    ap.add_argument("--backend", choices=("schtasks", "powershell", "manual"),
                    help="强制指定调度后端，默认自动探测")
    a = ap.parse_args()
    if a.status:
        return status()
    if a.uninstall:
        return uninstall()
    return install(a.every, a.backend, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
