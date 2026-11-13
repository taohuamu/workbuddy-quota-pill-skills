#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能包校验器：不依赖 PyYAML，只做本技能用到的结构检查。

检查项：
- frontmatter 存在且可解析
- name 必填、与目录同名、符合 [a-z0-9-] 规则、无连续连字符
- description 非空且 ≤1024 字符，含「何时使用」的表述
- 正文不超过 500 行（超过 80 行给提示）
- 正文引用的 references/ 文件真实存在
- scripts/ 下的脚本能被 python 语法编译通过

用法：python tools/validate_skill.py quota-pill/SKILL.md
"""
import os
import py_compile
import re
import sys
import tempfile

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    if not m:
        raise SystemExit("FAIL: 缺少 YAML frontmatter")
    fields = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if mm:
            fields[mm.group(1)] = mm.group(2).strip()
    return fields, m.group(2)


def main(path):
    root = os.path.dirname(os.path.abspath(path))
    text = open(path, encoding="utf-8").read()
    fields, body = parse_frontmatter(text)
    ok, warns = True, []

    name = fields.get("name", "")
    if not name:
        print("FAIL  name 缺失"); ok = False
    elif name != os.path.basename(root):
        print("FAIL  name(%s) 与目录名(%s) 不一致" % (name, os.path.basename(root))); ok = False
    elif not NAME_RE.match(name):
        print("FAIL  name 不合规：仅小写字母/数字/连字符，且不得以连字符开头结尾或连续")
        ok = False

    desc = fields.get("description", "")
    if not desc:
        print("FAIL  description 缺失"); ok = False
    elif len(desc) > 1024:
        print("FAIL  description %d 字符，超过 1024" % len(desc)); ok = False
    if desc and ("使用" not in desc and "Use when" not in desc):
        warns.append("description 未出现「使用/Use when」，可能缺少触发条件")

    lines = len(body.strip().splitlines())
    if lines > 500:
        print("FAIL  正文 %d 行，超过 500" % lines); ok = False
    elif lines > 80:
        warns.append("正文 %d 行，建议收在 80 行内" % lines)

    for ref in sorted(set(re.findall(r"references/[A-Za-z0-9_.-]+\.md", text))):
        if not os.path.exists(os.path.join(root, ref)):
            print("FAIL  引用的文件不存在：%s" % ref); ok = False

    for fn in sorted(os.listdir(os.path.join(root, "scripts")) if os.path.isdir(
            os.path.join(root, "scripts")) else []):
        if not fn.endswith(".py"):
            continue
        try:
            py_compile.compile(os.path.join(root, "scripts", fn),
                               cfile=os.path.join(tempfile.gettempdir(), fn + "c"),
                               doraise=True)
        except py_compile.PyCompileError as e:
            print("FAIL  脚本语法错误：%s\n%s" % (fn, e)); ok = False

    print("name            :", name or "(缺失)")
    print("description 长度 :", len(desc))
    print("正文行数         :", lines)
    print("allowed-tools   :", fields.get("allowed-tools", "(未设置)"))
    for w in warns:
        print("WARN ", w)
    print("\n结果:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "quota-pill/SKILL.md"))
