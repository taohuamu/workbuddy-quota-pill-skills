#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输出层契约测试：确保技能渲染出来的表，与数据层的报告一致。

这些断言针对的是「格式化时会不会漏掉模型、写错数字、把旧周期算进来」，
而不是数据层本身（数据层由主项目的 tests/test_core.py 覆盖）。

运行：python tools/test_output_contract.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "quota-pill")
REPORT = os.path.join(SKILL, "scripts", "quota_report.py")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def run(script, *args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, script, *args],
                          capture_output=True, text=True, encoding="utf-8", env=e)


def main():
    # 1. JSON 能出来，结构完整
    r = run(REPORT, "--json", "--no-cache")
    check("--json 退出码为 0 或 1", r.returncode in (0, 1), "rc=%d" % r.returncode)
    try:
        blob = json.loads(r.stdout)
    except ValueError as e:
        check("--json 输出可解析", False, str(e))
        return finish()
    check("--json 输出可解析", True)
    rep = blob["report"]
    models = rep.get("models", [])
    live = [m for m in models if not m.get("stale")]
    stale = [m for m in models if m.get("stale")]
    check("报告含 models 字段", "models" in rep)

    # 2. 表格渲染：表头、行数、数字一致
    t = run(REPORT, "--no-cache")
    text = t.stdout
    header = "| 模型 | 已用 | 本周期重置 | 近 15 分钟 | 按此速度 | 数据新鲜度 |"
    check("表头完整", header in text)
    check("表头含观测列", "近 15 分钟" in text)
    check("表头含读数列", "按此速度" in text)
    check("旧的「可信度」列已移除", "可信度" not in text)
    body = [ln for ln in text.splitlines() if ln.startswith("| `")]
    check("表体行数 = 本周期模型数", len(body) == len(live),
          "表体 %d / live %d" % (len(body), len(live)))
    for m in live:
        row = [ln for ln in body if "`%s`" % m["model"] in ln]
        if not row:
            check("模型 %s 出现在表体" % m["model"], False)
            continue
        cell = row[0].split("|")[2].strip()
        check("模型 %s 百分比一致" % m["model"], cell == "%g%%" % m["percent_used"],
              "表体 %s vs 报告 %g" % (cell, m["percent_used"]))

    # 3. 旧周期模型不能被算进表体
    for m in stale:
        check("旧周期模型 %s 不出现" % m["model"],
              ("`%s`" % m["model"]) not in text)

    # 4. 末行必须带取数耗时与日志目录
    check("末行含取数耗时", "取数" in text)
    check("末行含日志目录", "日志目录" in text)

    # 4b. 正文只说结果：不报格数、不报速率、不承诺「X 小时内」
    notice = [ln for ln in text.splitlines() if ln.startswith("**注意**")]
    joined = " ".join(notice)
    check("注意行不报格数", "格" not in joined, joined[:60])
    check("注意行不报速率", "/小时" not in joined and "格/小时" not in joined, joined[:60])
    check("注意行不承诺「X 小时内触限」", "小时内触限" not in joined, joined[:60])

    # 5. 缓存：第二次应命中
    run(REPORT)
    t2 = run(REPORT)
    check("第二次命中缓存", "命中缓存" in t2.stdout)
    t3 = run(REPORT, "--no-cache")
    check("--no-cache 强制重扫", "重新扫描" in t3.stdout)

    # 6. 空日志目录：要有可读的降级说明，而不是 Traceback
    with tempfile.TemporaryDirectory() as empty:
        r2 = run(REPORT, "--no-cache", env={"WORKBUDDY_HOME": empty})
        out = r2.stdout + r2.stderr
        check("空目录不抛栈", "Traceback" not in out, out.splitlines()[:1])
        check("空目录有提示", "没有找到" in out)

    # 7. 内置数据层与主项目同源
    s = run(os.path.join(SKILL, "scripts", "sync_check.py"))
    check("内置 quota_watch 与主项目同源", s.returncode == 0, s.stdout.strip()[:80])

    return finish()


def finish():
    ok = sum(1 for _, c, _ in results if c)
    for name, cond, detail in results:
        print(("PASS  " if cond else "FAIL  ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    print("\n%d/%d 通过" % (ok, len(results)))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
