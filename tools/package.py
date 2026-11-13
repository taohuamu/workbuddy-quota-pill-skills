#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打技能包：把 quota-pill 技能和安装脚本打成一个 zip，给另一台机器试装。

用法：
    python tools/package.py                      # 版本取自 SKILL.md，次数自增
    python tools/package.py --tag v0.4.1-test2
    python tools/package.py --skip-tests         # 跳过打包前自检（不推荐）

为什么要白名单：仓库里还有 route_test.md、两个测试脚本和 .git，
这些在别人的机器上没有意义，只会让人不知道该点哪个文件。
`START-HERE.txt` 与 `MANIFEST.txt` 是打包装时才生成的，不进仓库——
它们描述的是「这个包」，不是「这个项目」，留着只会和下一版对不上。
"""
import argparse
import datetime as dt
import hashlib
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "quota-pill")
OUT_ROOT = os.path.join(ROOT, "dist")

# 分发物清单。quota-pill/ 整个目录进包，tools/ 只放安装脚本。
INCLUDE_DIRS = ["quota-pill"]
INCLUDE_FILES = ["README.md", os.path.join("tools", "install.py")]

# 不该进包的东西：字节码无用，.git 会把仓库历史一起带走，dist 会自我嵌套。
SKIP_DIRS = {"__pycache__", ".git", "dist", ".idea", ".vscode"}
SKIP_EXT = {".pyc", ".pyo"}

START_HERE = """quota-pill 技能 · 试装说明
==========================

这是一个 WorkBuddy 技能：在对话里问「还剩多少额度」，直接拿到各模型的周期配额表。
只读本机的 WorkBuddy 会话日志，不联网、不登录、不改文件。

前提
----
1. Windows，且这台机器上的 WorkBuddy 已经聊过天 —— 没有会话日志就没有数据。
2. Python 3.8 以上，命令行里 `python --version` 能出版本号。
   出不来就试 `py --version`；两个都不行，先装 Python 再来。

装
--
1. 解压到任意目录，例如 D:\\quota-pill-test
2. 打开命令提示符，进到解压出来的那一层（能看到 quota-pill 和 tools 两个文件夹）
3. 执行：

       python tools\\install.py --copy

   用 --copy 而不是默认的目录联接：这个解压目录回头删掉，也不会留下一个指向
   空路径的安装。默认方式要求这个文件夹长期留着。
4. 新开一个 WorkBuddy 会话（技能清单在会话启动时加载，当前会话装了也不会立刻出现）
5. 问一句：现在还剩多少额度

   应出现一张表，列为：模型 / 已用 / 本周期重置 / 增速 / 预计触限 / 可信度 / 数据新鲜度。

不看对话、先验证数据能不能取到
------------------------------
    python quota-pill\\scripts\\quota_report.py

正常会直接打印同一张表，末行带取数耗时和日志目录。

没反应怎么办
------------
- 表格没出现，但上面那条命令能打印表 → 技能装好了，是没被选中。
  换一句话问，比如「各模型配额还剩多少」，或直接说「用 quota-pill 查一下」。
- 上面那条命令报「没有找到会话日志」→ 这台机器的 WorkBuddy 还没产生日志，
  先聊一轮再试。
- 报找不到 python → 命令换成 py，或把 Python 加进 PATH。

卸载
----
    python tools\\install.py --uninstall

它会先删提醒用的计划任务（如果装过），再删技能目录。
提醒功能默认不装，要用的时候单独执行 quota-pill\\scripts\\install_task.py，
细节见 README.md。
"""


def version():
    """从 SKILL.md 的 metadata.version 取，取不到就退回日期。"""
    try:
        text = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    except OSError:
        return "0.0.0"
    m = re.search(r'^\s+version:\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else "0.0.0"


def iter_files():
    """产出 (磁盘路径, 包内相对路径)。白名单 + 跳过字节码。"""
    for name in INCLUDE_FILES:
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            yield path, name.replace(os.sep, "/")
    for top in INCLUDE_DIRS:
        base = os.path.join(ROOT, top)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                    continue
                path = os.path.join(dirpath, fn)
                yield path, os.path.relpath(path, ROOT).replace(os.sep, "/")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight():
    """打包前跑自检：技能结构校验 + 输出层契约。任一失败就不出包——
    一个装不上的包比没有包更糟，对方会以为是环境问题。"""
    steps = [
        ("技能结构校验", [os.path.join(HERE, "validate_skill.py"),
                          os.path.join(SKILL, "SKILL.md")]),
        ("输出层契约", [os.path.join(HERE, "test_output_contract.py")]),
    ]
    for label, cmd in steps:
        r = subprocess.run([sys.executable, *cmd], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        tail = (r.stdout or r.stderr).strip().splitlines()
        if r.returncode != 0:
            print("自检失败：%s" % label)
            print("\n".join(tail[-8:]))
            print("\n修完再打包，或用 --skip-tests 强行出包。")
            return False
        print("自检通过：%s  %s" % (label, tail[-1] if tail else ""))
    return True


def build(tag):
    top = "workbuddy-quota-pill-skills-%s" % version()
    os.makedirs(OUT_ROOT, exist_ok=True)
    out = os.path.join(OUT_ROOT, "%s-%s.zip" % (top, tag))

    files = list(iter_files())
    if not files:
        print("没有可打包的文件，检查 quota-pill/ 是否存在。")
        return 1

    manifest = ["# 本包文件清单（sha256）", "# 拷贝过程中如果被改动或截断，哈希会对不上", ""]
    for path, rel in files:
        manifest.append("%s  %s" % (sha256(path), rel))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, rel in files:
            z.write(path, top + "/" + rel)
        # 这两个是给收包的人看的，放在最外层，解压就能看到。
        z.writestr(top + "/START-HERE.txt",
                   "\ufeff" + START_HERE.replace("\n", "\r\n"))
        z.writestr(top + "/MANIFEST.txt",
                   "\ufeff" + "\r\n".join(manifest) + "\r\n")

    size = os.path.getsize(out)
    print("已生成：%s  （%d 个文件，%.0f KB）" % (out, len(files) + 2, size / 1024.0))
    return 0 if verify(out, top, files) else 1


def verify(out, top, files):
    """重新打开 zip 核对：该在的在，不该在的没混进来，哈希一致。"""
    bad = []
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        for _, rel in files:
            if top + "/" + rel not in names:
                bad.append("缺文件 " + rel)
        for name in names:
            if "__pycache__" in name or name.endswith((".pyc", ".pyo")):
                bad.append("混入字节码 " + name)
            if "/.git/" in name or name.endswith("/.git"):
                bad.append("混入仓库历史 " + name)
        for need in ("SKILL.md", "START-HERE.txt", "MANIFEST.txt", "install.py"):
            if not any(n.endswith("/" + need) for n in names):
                bad.append("缺 " + need)
        # 关键文件逐字节复核，确认写入时没被编码或换行改动
        for _, rel in files:
            if sha256_from_zip(z, top + "/" + rel) != sha256(
                    os.path.join(ROOT, rel.replace("/", os.sep))):
                bad.append("内容不一致 " + rel)

    if bad:
        print("\n包校验未通过：")
        for b in dict.fromkeys(bad):
            print("  - " + b)
        return False
    print("包校验通过：文件齐全、无字节码、哈希与源文件一致。")
    return True


def sha256_from_zip(z, name):
    h = hashlib.sha256()
    with z.open(name) as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=dt.date.today().strftime("%Y%m%d"),
                    help="包名后缀，默认今天日期")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()

    if not args.skip_tests and not preflight():
        return 1
    return build(args.tag)


if __name__ == "__main__":
    sys.exit(main())
