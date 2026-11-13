"""注册 / 注销「配额阈值提醒」的 Windows 计划任务。

提醒脚本本身不常驻：计划任务每 N 分钟拉起一次，跑完立即退出。
命中阈值时弹一次系统气泡，其余时间什么也不做。

    python tools/install_task.py            # 安装（默认每 10 分钟）
    python tools/install_task.py --every 5   # 改间隔
    python tools/install_task.py --status    # 查看
    python tools/install_task.py --uninstall # 卸载
"""

import argparse
import os
import subprocess
import sys

TASK_NAME = "WorkBuddyQuotaPill-Notify"
HERE = os.path.dirname(os.path.abspath(__file__))
NOTIFY = os.path.join(HERE, "notify.py")


def python_for_task():
    """优先用 pythonw.exe，计划任务拉起时不会闪黑框。"""
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def run(args):
    """schtasks 可能被安全策略直接拦死（进程起不来），此时不要抛栈，
    退化成「返回失败」让调用方打印手动命令。"""
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def status():
    r = run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"])
    if r.returncode != 0:
        print("未安装")
        return 1
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith(("TaskName", "任务名", "Status", "状态", "Next Run", "下次运行", "Task To Run", "要运行的任务")):
            print("  " + line)
    print("\n提醒脚本:", NOTIFY)
    print("解释器  :", python_for_task())
    return 0


def install(every):
    if not os.path.exists(NOTIFY):
        print("找不到提醒脚本:", NOTIFY)
        return 1
    tr = '"%s" "%s"' % (python_for_task(), NOTIFY)
    r = run(["schtasks", "/Create", "/TN", TASK_NAME, "/TR", tr,
             "/SC", "MINUTE", "/MO", str(every), "/IT", "/F"])
    if r.returncode != 0:
        print("安装失败:", (r.stderr or r.stdout).strip())
        # 手动执行时 /TR 的整串要再包一层引号，内部两个路径各自转义，
        # 否则 schtasks 只认第一个路径，后面的被当成多余参数。
        manual = '"\\"%s\\" \\"%s\\""' % (python_for_task(), NOTIFY)
        print("\n在命令提示符里手动执行（不需要管理员）：")
        print('schtasks /Create /TN "%s" /TR %s /SC MINUTE /MO %d /IT /F'
              % (TASK_NAME, manual, every))
        return 1
    print("已安装：每 %d 分钟检查一次，仅在当前用户登录时运行" % every)
    status()
    return 0


def uninstall():
    r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if r.returncode != 0:
        print("卸载失败或本来就不存在:", (r.stderr or r.stdout).strip())
        return 1
    print("已卸载计划任务")
    return 0


def main():
    ap = argparse.ArgumentParser(description="配额提醒计划任务")
    ap.add_argument("--every", type=int, default=10, help="检查间隔（分钟）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    if a.status:
        return status()
    if a.uninstall:
        return uninstall()
    return install(a.every)


if __name__ == "__main__":
    sys.exit(main())
