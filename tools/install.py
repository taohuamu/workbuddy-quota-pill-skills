#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 quota-pill 技能装到 WorkBuddy 的技能目录。

Windows 下默认建「目录联接」（junction），这样工作区里改完即时生效，
不必每次重装；非 Windows 或加了 --copy 时退回整目录复制。

用法：
    python tools/install.py            # 安装（默认 junction）
    python tools/install.py --copy     # 安装（复制一份）
    python tools/install.py --uninstall
    python tools/install.py --status
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "quota-pill")

# 任务名只应该有一个定义处，就是 install_task.py；这里优先取它的值，
# 取不到（技能目录被人拆散）才退回内置常量，避免改名后两处不一致。
sys.path.insert(0, os.path.join(SRC, "scripts"))
try:
    from install_task import TASK_NAME
except Exception:                                  # noqa: BLE001
    TASK_NAME = "WorkBuddyQuotaPill-Notify"


def target_root():
    return os.path.join(os.path.expanduser("~"), ".workbuddy", "skills")


def target_dir():
    return os.path.join(target_root(), "quota-pill")


def is_junction(path):
    """目录联接/符号链接：realpath 会解析到源目录，普通复制不会。"""
    try:
        return os.path.realpath(path).lower() != os.path.abspath(path).lower()
    except OSError:
        return False


def make_junction(link, dest):
    r = subprocess.run(["cmd", "/c", "mklink", "/J", link, dest],
                       capture_output=True, text=True,
                       encoding="gbk", errors="ignore")
    return r.returncode == 0


def do_install(copy_mode):
    dst = target_dir()
    os.makedirs(target_root(), exist_ok=True)
    if os.path.exists(dst):
        print("目标已存在：%s" % dst)
        print("先执行 --uninstall 再装。")
        return 1
    if not copy_mode and sys.platform == "win32" and make_junction(dst, SRC):
        print("已建目录联接：%s -> %s" % (dst, SRC))
        print("工作区改动即时生效，无需重装。")
    else:
        # 不能把 __pycache__ 复制过去：分发物里混进 .pyc 既无用又会被扫描器当垃圾。
        shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo"))
        print("已复制到：%s" % dst)
        print("注意：复制方式下，工作区改动需要重新安装才生效。")
    print("\n验证：新开一个会话，问「现在还剩多少额度」，应出现 7 列表格。")
    print("卸载：python tools/install.py --uninstall")
    return 0


def _schtasks(args):
    """调用 schtasks。可能抛 OSError：本机若把它列入程序黑名单，进程根本起不来。"""
    return subprocess.run(["schtasks"] + args, capture_output=True, text=True,
                          encoding="gbk", errors="ignore")


def task_status():
    """返回 'present' / 'absent' / 'blocked'（无法执行，判不了）。"""
    try:
        r = _schtasks(["/Query", "/TN", TASK_NAME])
    except OSError:
        return "blocked"
    return "present" if r.returncode == 0 else "absent"


def remove_task():
    """删除提醒用的计划任务。返回 'deleted' / 'absent' / 'blocked' / 'failed'。"""
    st = task_status()
    if st != "present":
        return st
    try:
        r = _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    except OSError:
        return "blocked"
    return "deleted" if r.returncode == 0 else "failed"


def do_uninstall():
    dst = target_dir()

    # 先删任务再删目录：反过来的话，两次操作之间若正好到点，任务会去拉一个
    # 已经不存在的脚本，往 notify.log 里留一条无意义的报错。
    task = remove_task()
    if task == "deleted":
        print("已删除计划任务：%s" % TASK_NAME)
    elif task in ("blocked", "failed"):
        # 判不了的时候，用状态文件当旁证：它只在 notify 跑过之后才存在。
        # 没跑过就说明提醒从未启用，不必拿一条可能并不存在的任务去打扰用户。
        state = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                             "quota-pill", "notify-state.json")
        if task == "failed" or os.path.exists(state):
            print("计划任务可能仍存在（%s）。请手动执行一次：" % (
                "本机禁止调用 schtasks" if task == "blocked" else "删除失败"))
            print('  schtasks /Delete /TN "%s" /F' % TASK_NAME)

    if not os.path.exists(dst):
        print("未安装：%s" % dst)
        return 0
    if is_junction(dst):
        os.rmdir(dst)          # 联接只删链接，不动源目录
        print("已移除联接（源目录未动）：%s" % dst)
    else:
        shutil.rmtree(dst)
        print("已删除：%s" % dst)
    return 0


def do_status():
    dst = target_dir()
    if not os.path.exists(dst):
        print("未安装")
        return 1
    kind = "目录联接" if is_junction(dst) else "复制"
    src_ok = os.path.exists(os.path.join(dst, "SKILL.md"))
    print("已安装（%s）：%s" % (kind, dst))
    print("SKILL.md 存在：%s" % src_ok)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        return do_status()
    if args.uninstall:
        return do_uninstall()
    return do_install(args.copy)


if __name__ == "__main__":
    sys.exit(main())
