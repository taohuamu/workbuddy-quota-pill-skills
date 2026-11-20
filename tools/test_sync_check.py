#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_check.py 的日期判据回归测试（无第三方依赖）。

守的是 R16 那个 Bug：原来拿 mtime 当「内容日期」，而 clone / 解压 / 复制都会把
mtime 刷成当下，于是每次重新 clone 都把全部 references 误报成「内容改过、日期没跟」。
现在的判据是「git 里有提交且工作树干净 → 用提交日期；否则退回 mtime」。

    python tools/test_sync_check.py
"""
import datetime as dt
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "quota-pill", "scripts"))

import sync_check as sc  # noqa: E402

PASS = FAIL = 0
FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL %s  %s" % (name, detail if detail else ""))


def touch_future(path, day="2026-11-25"):
    """把 mtime 推到未来某天 —— 模拟「重新 clone 出来的文件」。"""
    stamp = dt.datetime.strptime(day, "%Y-%m-%d").replace(hour=9).timestamp()
    os.utime(path, (stamp, stamp))


def git(folder, *args, **env_extra):
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-11-20T10:00:00",
               GIT_COMMITTER_DATE="2026-11-20T10:00:00")
    env.update(env_extra)
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@t",
           "-c", "commit.gpgsign=false"] + list(args)
    out = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise RuntimeError("git %s 失败：%s" % (" ".join(args), out.stderr.strip()))
    return out.stdout


def make_ref(root, name="a.md", text="> 上次核对：2026-11-20\n\n正文\n"):
    folder = os.path.join(root, "references")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return folder, path


def test_clean_repo_ignores_mtime():
    """clone 出来的文件：mtime 变了，但最后一次提交还是 11-20 → 不该报。"""
    with tempfile.TemporaryDirectory() as root:
        folder, path = make_ref(root)
        git(root, "init", "-q")
        git(root, "add", "references/a.md")
        git(root, "commit", "-q", "-m", "init")
        touch_future(path, "2026-11-25")
        got, source = sc.content_date(path)
        check("干净工作树取提交日期", got == dt.date(2026, 11, 20), "%s / %s" % (got, source))
        check("clone 不改判据 → 无提醒", sc.check_reference_dates(folder) == [],
              sc.check_reference_dates(folder))


def test_dirty_file_uses_mtime():
    """真改了内容没提交：mtime 才是证据，必须报出来。"""
    with tempfile.TemporaryDirectory() as root:
        folder, path = make_ref(root)
        git(root, "init", "-q")
        git(root, "add", "references/a.md")
        git(root, "commit", "-q", "-m", "init")
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n补一句\n")
        touch_future(path, "2026-11-25")
        problems = sc.check_reference_dates(folder)
        check("脏文件报提醒", len(problems) == 1, problems)
        check("提醒里说明按 mtime", bool(problems) and "未提交改动" in problems[0], problems)


def test_no_git_falls_back_to_mtime():
    """不在 git 仓库里（比如解压出来的技能包）：退回 mtime，不能崩。"""
    with tempfile.TemporaryDirectory() as root:
        folder, path = make_ref(root)
        touch_future(path, "2026-11-25")
        got, source = sc.content_date(path)
        check("无 git 时用 mtime", got == dt.date(2026, 11, 25), "%s / %s" % (got, source))
        check("无 git 时也能报提醒", len(sc.check_reference_dates(folder)) == 1)


def test_date_not_older_is_quiet():
    """头部日期比内容新 → 不报（允许提前写日期）。"""
    with tempfile.TemporaryDirectory() as root:
        folder, path = make_ref(root, text="> 上次核对：2026-12-31\n")
        touch_future(path, "2026-11-25")
        check("日期较新不提醒", sc.check_reference_dates(folder) == [])


def test_missing_and_broken_date():
    """没有「上次核对」→ 跳过；日期写坏 → 报「无法解析」而不是崩。"""
    with tempfile.TemporaryDirectory() as root:
        folder, _ = make_ref(root, name="none.md", text="# 没有日期\n")
        check("缺日期行视为通过", sc.check_reference_dates(folder) == [])
        folder2, _ = make_ref(os.path.join(root, "b"), text="> 上次核对：2026-13-45\n")
        problems = sc.check_reference_dates(folder2)
        check("坏日期报无法解析",
              len(problems) == 1 and "无法解析" in problems[0], problems)


def test_missing_dir_is_safe():
    check("目录不存在返回空", sc.check_reference_dates("/no/such/dir") == [])
    check("None 也安全", sc.check_reference_dates(None) == [])


if __name__ == "__main__":
    print("sync_check 日期判据回归测试")
    for fn in (test_clean_repo_ignores_mtime, test_dirty_file_uses_mtime,
               test_no_git_falls_back_to_mtime, test_date_not_older_is_quiet,
               test_missing_and_broken_date, test_missing_dir_is_safe):
        print("\n[%s]" % fn.__name__)
        fn()
    print("\n%d/%d 通过" % (PASS, PASS + FAIL))
    if FAILED:
        print("失败：", ", ".join(FAILED))
    sys.exit(1 if FAIL else 0)
