#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install_task.py 的运行副本判据测试。

只测「副本是否落后」这一件事：它决定 `--status` 会不会让人重跑安装。
用临时 RUNTIME_DIR，不碰真实的任务、不注册任何东西。

运行：python tools/test_install_task.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "quota-pill", "scripts")
sys.path.insert(0, SCRIPTS)

import install_task as it  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def flip_byte(path):
    """把文件中间的一个字节换个值，长度不变（模拟「改了一个字符」的编辑）。"""
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    i = len(data) // 2
    data[i] = data[i] ^ 0x01
    with open(path, "wb") as fh:
        fh.write(bytes(data))


def main():
    tmp = tempfile.mkdtemp(prefix="quota-pill-stage-")
    old = it.RUNTIME_DIR
    try:
        it.RUNTIME_DIR = tmp
        it.stage_runtime()
        check("刚部署完不算落后", it.staged_is_stale() is False)

        # [B1] 同大小改动必须被发现：只比大小时这里会返回 False
        target = os.path.join(tmp, "forecast.py")
        size_before = os.path.getsize(target)
        flip_byte(target)
        check("改了一个字节但长度不变 → 判落后",
              os.path.getsize(target) == size_before and it.staged_is_stale() is True,
              "size %d -> %d" % (size_before, os.path.getsize(target)))

        it.stage_runtime()
        check("重新部署后不再落后", it.staged_is_stale() is False)

        # 改名前（quota_watch.py → quota_pill.py）部署过的用户：旧模块不能留在 runtime，
        # 否则会躺一份没人 import 的副本，排查时容易看错文件。
        legacy = os.path.join(tmp, "quota_watch.py")
        with open(legacy, "w", encoding="utf-8") as fh:
            fh.write("# 旧版数据层\n")
        it.stage_runtime()
        check("部署时清掉改名前留下的旧模块", not os.path.exists(legacy))

        os.remove(os.path.join(tmp, "notify.py"))
        check("副本缺文件 → 判落后", it.staged_is_stale() is True)
    finally:
        it.RUNTIME_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)

    # 源文件缺失：STAGE_FILES 里有一项在技能目录里不存在 → 视为落后（无法确认一致）
    tmp2 = tempfile.mkdtemp(prefix="quota-pill-stage2-")
    try:
        it.RUNTIME_DIR = tmp2
        it.stage_runtime()
        src = os.path.join(it.HERE, it.STAGE_FILES[0])
        hidden = src + ".hidden"
        os.rename(src, hidden)
        try:
            check("源文件缺失 → 判落后", it.staged_is_stale() is True)
        finally:
            os.rename(hidden, src)
    finally:
        it.RUNTIME_DIR = old
        shutil.rmtree(tmp2, ignore_errors=True)

    ok = 0
    for name, passed, detail in results:
        print(("PASS  " if passed else "FAIL  ") + name + ("" if passed else "  " + str(detail)))
        ok += 1 if passed else 0
    print("\n%d/%d 通过" % (ok, len(results)))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
