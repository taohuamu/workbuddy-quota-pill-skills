# -*- coding: utf-8 -*-
"""探测本机可用的任务调度后端，供 install_task.py 选路。

背景：`schtasks.exe` 在部分环境里会被安全策略直接拦死（进程起不来，
Python 侧只看到 PermissionError / WinError 5），而 PowerShell 的
ScheduledTasks 模块走的是 CIM 调用，常见环境下不受同一条黑名单影响。

用法：
    python probe_scheduler.py           # 人类可读
    python probe_scheduler.py --json    # 机器可读，供其它脚本消费

退出码：0 至少有一个可用后端；1 都不可用（只能把命令交给用户手动执行）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

PS_EXE = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _powershell(script, timeout=25):
    """跑一段 PowerShell。返回 (returncode, stdout, stderr)；起不来则 (None, '', 原因)。"""
    exe = PS_EXE if os.path.exists(PS_EXE) else shutil.which("powershell")
    if not exe:
        return None, "", "找不到 powershell.exe"
    try:
        r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, "", str(e)
    # 中文 Windows 上控制台输出是 GBK；写死 utf-8 会把错误文本变成乱码。
    out = r.stdout.decode("gbk", "replace")
    err = r.stderr.decode("gbk", "replace")
    return r.returncode, out, err


def probe_powershell():
    """一次调用同时确认三件事：powershell 可执行、ScheduledTasks 模块在、是否管理员。"""
    script = (
        "$m = if (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue) {'1'} else {'0'}; "
        "$p = New-Object Security.Principal.WindowsPrincipal("
        "[Security.Principal.WindowsIdentity]::GetCurrent()); "
        "$a = if ($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {'1'} else {'0'}; "
        "\"ps=ok;module=$m;admin=$a\""
    )
    rc, out, err = _powershell(script)
    if rc is None:
        return {"powershell": "missing", "scheduledtasks": "missing",
                "admin": False, "detail": err}
    if rc != 0:
        return {"powershell": "error", "scheduledtasks": "missing",
                "admin": False, "detail": (err or out).strip()[:200]}
    fields = dict(part.split("=", 1) for part in out.strip().split(";") if "=" in part)
    return {
        "powershell": "ok",
        "scheduledtasks": "ok" if fields.get("module") == "1" else "missing",
        "admin": fields.get("admin") == "1",
    }


def probe_schtasks():
    """返回 ok / blocked / error。blocked 指进程根本起不来（黑名单、策略、无执行权限）。"""
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", "__probe_does_not_exist__"],
                           capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"schtasks": "blocked", "detail": "%s: %s" % (type(e).__name__, e)}
    # 任务不存在时 schtasks 返回 1，说明它本身是可用的。
    return {"schtasks": "ok" if r.returncode in (0, 1) else "error"}


def probe():
    result = {}
    result.update(probe_schtasks())
    result.update(probe_powershell())
    if result.get("schtasks") == "ok":
        result["recommended"] = "schtasks"
    elif result.get("scheduledtasks") == "ok":
        result["recommended"] = "powershell"
    else:
        result["recommended"] = "manual"
    return result


def main():
    ap = argparse.ArgumentParser(description="探测可用的任务调度后端")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = probe()
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("schtasks      : %s" % r.get("schtasks"))
        print("powershell    : %s" % r.get("powershell"))
        print("ScheduledTasks: %s" % r.get("scheduledtasks"))
        print("管理员        : %s" % ("是" if r.get("admin") else "否"))
        print("推荐后端      : %s" % r["recommended"])
        if r.get("detail"):
            print("细节          : %s" % r["detail"])
    return 0 if r["recommended"] != "manual" else 1


if __name__ == "__main__":
    sys.exit(main())
