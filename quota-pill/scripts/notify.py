"""配额阈值提醒：读本地配额快照，接近耗尽时发一条系统通知。

只读本地会话日志，不联网、不写 WorkBuddy 的任何数据。
由 Windows 计划任务或 WorkBuddy 定时任务调用，进程跑完即退出。

用法：
    python notify.py                # 正常检查，命中阈值才弹
    python notify.py --dry-run      # 只打印判定，不弹窗
    python notify.py --force        # 忽略冷却，强制弹一次（调试用）
    python notify.py --cooldown 60  # 同一模型同一等级多少分钟内不重复提醒
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_watch as qw
import phrasing

STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "quota-pill")
STATE_FILE = os.path.join(STATE_DIR, "notify-state.json")

LEVEL_CN = {"critical": "危险", "warn": "注意"}
LEVEL_RANK = {"critical": 0, "warn": 1, "ok": 2, "idle": 3}
LOG_FILE = os.path.join(STATE_DIR, "notify.log")
LOG_MAX = 200 * 1024


def log(msg):
    """计划任务用 pythonw 拉起时没有 stdout，print 会抛 AttributeError；
    此时改写日志文件，两种情况下都能留下痕迹。"""
    if sys.stdout is not None:
        try:
            print(msg)
            return
        except Exception:
            pass
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX:
            os.replace(LOG_FILE, LOG_FILE + ".1")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- 状态

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError:
        pass


# ---------------------------------------------------------------- 判定

def pick_alerts(models):
    """取本周期内 level 为 critical / warn 的模型，危险优先。"""
    hits = [m for m in models if not m.get("stale") and m.get("level") in LEVEL_CN]
    hits.sort(key=lambda m: (LEVEL_RANK[m["level"]], -m["percent_used"]))
    return hits


# 一句话文案统一在 phrasing.py（报告和通知共用同一句），这里只负责排版与送达。


def filter_cooldown(hits, state, cooldown_min, force):
    """同一模型同一等级在冷却期内不重复提醒；等级升级（warn→critical）仍会提醒。"""
    if force:
        return hits
    now = time.time()
    out = []
    for m in hits:
        prev = state.get(m["model"]) or {}
        same = prev.get("level") == m["level"]
        fresh = now - float(prev.get("at") or 0) < cooldown_min * 60
        if same and fresh:
            continue
        out.append(m)
    return out


def remember(hits, state):
    now = time.time()
    for m in hits:
        state[m["model"]] = {"level": m["level"], "at": now,
                             "percent": m["percent_used"], "verdict": m["verdict"]}
    save_state(state)


# ---------------------------------------------------------------- 通知

# 借 PowerShell 的 AppUserModelID 发通知。系统 toast 的停留时长由系统决定，
# 旧式托盘气泡在 Win10/11 上会被压缩成一闪，实测抓不到，所以这里优先走 toast。
PS_APPID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

PS_TOAST = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast duration="long"><visual><binding template="ToastText02"><text id="1">' + $env:QP_TITLE + '</text><text id="2">' + $env:QP_BODY + '</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:QP_APPID).Show($toast)
"""


def toast(title, body):
    """发一条系统通知。文本经 XML 转义后由环境变量传入，不拼进脚本。"""
    if os.name != "nt":
        return False
    try:
        from xml.sax.saxutils import escape
    except ImportError:
        return False
    env = dict(os.environ)
    env["QP_TITLE"] = escape(title[:60])
    env["QP_BODY"] = escape(body[:200])
    env["QP_APPID"] = PS_APPID
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", PS_TOAST],
            capture_output=True, text=True, env=env, timeout=25,
            creationflags=0x08000000)          # CREATE_NO_WINDOW，别闪黑框
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


# ---------------------------------------------------------------- 气泡

class _NID(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
        ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
    ]


NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_INFO = 0x10
NIIF_WARNING = 0x02


def balloon(title, body, hold_sec=8.0):
    """弹一个托盘气泡并保持进程存活，让气泡有足够时间被看到。"""
    if os.name != "nt":
        return False
    u32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32

    hwnd = u32.CreateWindowExW(0, "STATIC", "quota-pill-notify", 0,
                               0, 0, 0, 0, None, None, None, None)
    if not hwnd:
        return False

    nid = _NID()
    nid.cbSize = ctypes.sizeof(_NID)
    nid.hWnd = hwnd
    nid.uID = 0x51
    nid.uFlags = NIF_INFO
    nid.szInfoTitle = title[:63]
    nid.szInfo = body[:255]
    nid.dwInfoFlags = NIIF_WARNING
    try:
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            return False
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        # 抽消息并定时，避免气泡因为进程立刻退出而被收回
        msg = wt.MSG()
        end = time.time() + hold_sec
        while time.time() < end:
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.1)
    finally:
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        u32.DestroyWindow(hwnd)
    return True


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="配额阈值提醒")
    ap.add_argument("--window", type=int, default=15, help="增速采样窗口（分钟）")
    ap.add_argument("--warn", type=float, default=3.0, help="预计触限小时数阈值")
    ap.add_argument("--cooldown", type=int, default=120, help="同一提醒的冷却分钟数")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不弹窗")
    ap.add_argument("--force", action="store_true", help="忽略冷却")
    args = ap.parse_args()

    report = qw.build_report(args.window, args.warn)
    models = report.get("models") or []
    if not models:
        log(report.get("error") or "没有可用的配额快照")
        return 0

    state = load_state()
    hits = pick_alerts(models)
    todo = filter_cooldown(hits, state, args.cooldown, args.force)

    stamp = dt.datetime.now().strftime("%H:%M:%S")
    log("[%s] 本周期 %d 个模型，命中 %d，待提醒 %d"
          % (stamp, sum(1 for m in models if not m.get("stale")), len(hits), len(todo)))

    if not todo:
        return 0

    # 一条一行。用「；」串成一行的话，长模型名会把折行位置挤到名字中间，
    # 断在哪儿不可控；自己换行，至少每条是完整的。
    lines = [phrasing.line(m) for m in todo[:2]]
    if len(todo) > 2:
        lines.append("另 %d 个模型需注意" % (len(todo) - 2))
    body = "\n".join(lines)

    if args.dry_run:
        log("  [dry-run] 配额胶囊 / " + body.replace("\n", " | "))
        return 0

    shown = toast("配额胶囊", body) or balloon("配额胶囊", body)
    log("  " + ("已发出通知：" if shown else "通知发送失败：") + body.replace("\n", " | "))
    if shown:
        remember(todo, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
