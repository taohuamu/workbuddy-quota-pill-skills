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

    # 2b. 包内 START-HERE.txt 的列头也必须与真实表头一致（R17 的 B23）
    #     它只存在于打包字符串里，不会出现在任何 .md 里，最容易漏。
    sys.path.insert(0, HERE)
    import package as pkg
    cols = [c.strip() for c in header.strip().strip("|").split("|")]
    missing = [c for c in cols if c not in pkg.START_HERE]
    check("试装说明列头与真实表头一致", not missing, missing)
    check("试装说明不再提旧的「增速 / 预计触限 / 可信度」",
          "可信度" not in pkg.START_HERE and "预计触限" not in pkg.START_HERE)
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

    # 6b. 全部模型都停在上一周期：不能报成「日志里没有带 quota 的行」（R14 的 B20）
    with tempfile.TemporaryDirectory() as old_home:
        proj = os.path.join(old_home, "projects", "case")
        os.makedirs(proj)
        now = time.time()
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({
                    "timestamp": now - 90000 + i * 60,
                    "providerData": {"model": "test-old", "rawUsage": {
                        "quota": {"model": "test-old", "percent": 40 + i,
                                  "reset_at": str(int(now - 3600))},
                        "credit": 1.0, "tokens": 10}}}, ensure_ascii=False) + "\n")
        r3 = run(REPORT, "--no-cache", env={"WORKBUDDY_HOME": old_home})
        check("全过期时不说「没有 quota 行」",
              "没有带 quota 的行" not in r3.stdout, r3.stdout.strip()[:80])
        check("全过期时说明是上一周期", "上一周期" in r3.stdout, r3.stdout.strip()[:80])

    # 7. 内置数据层与主项目同源
    s = run(os.path.join(SKILL, "scripts", "sync_check.py"))
    check("内置 quota_pill 与主项目同源", s.returncode == 0, s.stdout.strip()[:80])

    # 8. 只读一次盘：报告与预测共用同一份快照（R6 的 B1）
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import quota_report as qr
    real = qr.qp.load_snapshots
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return real()

    qr.qp.load_snapshots = counting
    try:
        qr.load_report(use_cache=False)
    finally:
        qr.qp.load_snapshots = real
    check("load_report 只读一次快照", calls["n"] == 1, "调用 %d 次" % calls["n"])

    # 8c. 缓存签名与写进缓存的报告同源（R12 的 B16）：本会话日志在扫描期间还在被追加，
    #     写缓存时重算签名 = 把「读后的签名」配上「读前的数据」，下次命中拿到残缺报告。
    seq = iter([["sig-A"], ["sig-B"], ["sig-C"]])
    real_sig, real_cache = qr.log_signature, qr.cache_file
    with tempfile.TemporaryDirectory() as cache_dir:
        cache_path = os.path.join(cache_dir, "c.json")
        # 先放一份签名对不上的旧缓存：这样才会走「比签名 → 重扫 → 写回」整条路，
        # 旧实现的两次 log_signature() 调用（查缓存一次、写缓存一次）才会暴露。
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"sig": ["stale"], "at": time.time(), "report": {}}, f)
        qr.log_signature = lambda: next(seq, ["sig-Z"])
        qr.cache_file = lambda: cache_path
        try:
            qr.load_report(use_cache=True)
            with open(cache_path, encoding="utf-8") as f:
                stored = json.load(f)["sig"]
        finally:
            qr.log_signature, qr.cache_file = real_sig, real_cache
    check("缓存签名与报告同源（取读盘前那次）", stored == ["sig-A"], stored)

    # 8d. 表头窗口跟报告走，不跟模块常量（R13 的 B19）
    fake = {"models": [{"model": "m", "percent_used": 10, "reset_local": "—",
                        "forecast": {"tier": "idle", "k": 0}, "last_seen_ts": 0}],
            "window_min": 45, "has_risk": False}
    head = qr.render(fake, False, 0.0).splitlines()[0]
    check("表头窗口取自报告的 window_min", "近 45 分钟" in head, head)

    # 8b. notify 侧同理（源码级：`load_snapshots` 只允许出现一次调用点）
    with open(os.path.join(SKILL, "scripts", "notify.py"), encoding="utf-8") as f:
        nsrc = f.read()
    check("notify 只有一个取快照调用点", nsrc.count("load_snapshots()") == 1,
          "出现 %d 次" % nsrc.count("load_snapshots()"))

    # 8e. 上架示例（「试试这样问我」）必须成对、无占位符、不带技能名（R19 的 B24）
    def _examples(key):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        out, on = [], False
        for ln in lines:
            if ln.startswith(key + ":"):
                on = True
                continue
            if on:
                if ln.startswith("- "):
                    out.append(ln[2:].strip().strip('"'))
                elif ln and not ln.startswith((" ", "\t")):
                    break
        return out

    zh, en = _examples("examples_zh"), _examples("examples_en")
    check("示例存在且中英成对", len(zh) >= 2 and len(zh) == len(en), "%d / %d" % (len(zh), len(en)))
    bad = [s for s in zh + en if "XX" in s or "xx" in s or "[" in s or "]" in s]
    check("示例不含占位符", not bad, bad)
    named = [s for s in zh + en if "quota-pill" in s or "配额胶囊" in s]
    check("示例不带技能名", not named, named)
    check("示例覆盖提醒场景", any("提醒" in s or "alert" in s.lower() for s in zh + en))
    # 上限是硬限制：4 条时上传直接被拒（「examples_zh 最多 3 个示例，当前 4 个」）
    check("示例不超过 3 条", len(zh) <= 3 and len(en) <= 3, "%d / %d" % (len(zh), len(en)))

    # 9. 高用量夹具：注意行出现，且两种模式的退出码一致（R7 的 B5）
    import datetime as _dt
    with tempfile.TemporaryDirectory() as hi:
        proj = os.path.join(hi, "projects", "case")
        os.makedirs(proj)
        now = time.time()
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as f:
            for i in range(6):
                f.write(json.dumps({
                    "timestamp": now - (5 - i) * 60,
                    "providerData": {"model": "test-hi", "rawUsage": {
                        "quota": {"model": "test-hi", "percent": 90 + i,
                                  "reset_at": str(int(now + 6 * 3600))},
                        "credit": 1.0, "tokens": 1000}}}, ensure_ascii=False) + "\n")
        env = {"WORKBUDDY_HOME": hi}
        hi_text = run(REPORT, "--no-cache", env=env)
        hi_json = run(REPORT, "--json", "--no-cache", env=env)
        check("高用量时文本退出码为 1", hi_text.returncode == 1, hi_text.returncode)
        check("高用量时 JSON 退出码同为 1", hi_json.returncode == 1, hi_json.returncode)
        check("高用量出现注意行", "**注意**" in hi_text.stdout, hi_text.stdout[-80:])
        check("高用量按此速度给出分钟数", "分钟后到上限" in hi_text.stdout, hi_text.stdout[-80:])

    # 10. README 声称的列数与实际表头一致（R7 的 B4）
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        rd = f.read()
    import re as _re
    said = _re.search(r"应出现 (\d) 列表格", rd)
    actual = len([c for c in header.strip().strip("|").split("|")])
    check("README 列数与表头一致",
          said is not None and int(said.group(1)) == actual,
          "README %s / 实际 %d" % (said.group(1) if said else "未写", actual))

    # 11. 帮助文本不再用内部单位「格」（R7 的 B6）
    nh = run(os.path.join(SKILL, "scripts", "notify.py"), "--help")
    check("notify --help 不用「格」", "格" not in nh.stdout, nh.stdout[-80:])
    check("notify --help 默认 2 小时", "默认 2" in nh.stdout, nh.stdout[-80:])

    # 12. SKILL.md 写的默认阈值必须与代码一致（R6 的 B3：曾写 1 小时，实际 2）
    with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
        sk = f.read()
    m = _re.search(r"阈值默认 (\d+)% / (\d+) 小时", sk)
    pct_ok = m and m.group(1) == "80"
    warn_ok = m and ("默认 %s" % m.group(2)) in nh.stdout
    check("SKILL.md 默认百分比 80%", bool(pct_ok), m.group(0) if m else "未写")
    check("SKILL.md 默认时限与 --help 一致", bool(warn_ok),
          (m.group(0) if m else "未写") + " / help=" + nh.stdout[-60:])

    # 13. README 结构树必须与磁盘一致（R9 的 B11：0.5.0 加了 forecast.py 没补树）
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        tree_block = f.read().split("```")[1]
    in_tree = set(_re.findall(r"[├└]──\s+([\w.\-]+\.py)", tree_block))
    on_disk = set()
    for d in (os.path.join(SKILL, "scripts"), os.path.join(ROOT, "tools")):
        for name in os.listdir(d):
            if name.endswith(".py"):
                on_disk.add(name)
    missing = sorted(on_disk - in_tree)
    extra = sorted(in_tree - on_disk)
    check("README 结构树含全部脚本", not missing, "缺 %s" % missing)
    check("README 结构树没有多余条目", not extra, "多 %s" % extra)
    check("README 结构树不写死测试项数",
          not _re.search(r"测试（\d+\s*项）", tree_block),
          "仍有「（N 项）」这类会漂移的数字")

    # 14. 坏行不能废掉整份报告（R10 边界用例）
    bad = tempfile.mkdtemp()
    try:
        proj = os.path.join(bad, "projects", "x")
        os.makedirs(proj)
        now = time.time()
        lines = [
            json.dumps({"timestamp": now, "providerData": {"model": "m1", "rawUsage": {
                "quota": {"model": "m1", "percent": "7%",
                          "reset_at": str(int(now + 7200))}}}}, ensure_ascii=False),
            "{ this is not json",
            "[]",
            json.dumps({"timestamp": None, "providerData": {"model": "m2", "rawUsage": {
                "quota": {"model": "m2", "percent": 3, "reset_at": "abc"}}}},
                ensure_ascii=False),
            json.dumps({"timestamp": now, "providerData": {"model": "m1", "rawUsage": {
                "quota": {"model": "m1", "percent": None,
                          "reset_at": str(int(now + 7200))}}}}, ensure_ascii=False),
        ]
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        rb = run(REPORT, "--no-cache", env={"WORKBUDDY_HOME": bad})
        out = rb.stdout + rb.stderr
        check("坏行不抛栈", "Traceback" not in out, out.splitlines()[:1])
        check("坏行之后仍能出表", "| `m1` |" in rb.stdout, out[-80:])
        check("带百分号的字符串也能解析", "| 7% |" in rb.stdout, out[-80:])
    finally:
        import shutil
        shutil.rmtree(bad, ignore_errors=True)

    # 15. 没有 forecast 时的兜底文案（VERDICT_TEXT 映射表已删，改成显式分支）
    code = "\n".join([
        "import phrasing",
        "print(phrasing.conclusion({'percent_used': 96, 'verdict': '已到上限，随时会被拒'}))",
        "print(phrasing.conclusion({'percent_used': 70, 'verdict': '重置前就会耗尽',"
        " 'eta_hours_to_limit': 2.0}))",
        "print(hasattr(phrasing, 'VERDICT_TEXT'))",
    ])
    rp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                        encoding="utf-8", cwd=os.path.join(SKILL, "scripts"))
    outs = (rp.stdout or "").strip().splitlines()
    check("无 forecast 时「已到上限」改口为即将触限",
          len(outs) >= 1 and outs[0] == "即将触限", outs)
    check("无 forecast 时带 eta 的耗尽句给时间",
          len(outs) >= 2 and outs[1] == "2 小时内触限", outs)
    check("VERDICT_TEXT 已删（不再留无消费方的映射表）",
          len(outs) >= 3 and outs[2] == "False", outs)

    # 16. 真路由清单里抄的表头必须与当前输出一致（列名改过一次，清单当年没跟着改）
    rt = os.path.join(HERE, "route_test.md")
    with open(rt, "r", encoding="utf-8") as f:
        rt_text = f.read()
    quoted = _re.findall(r"表头 `([^`\n]+)`", rt_text)
    real_head = next((ln.strip() for ln in run(REPORT, "--no-cache").stdout.splitlines()
                      if ln.startswith("| 模型")), "")
    check("route_test.md 抄的表头与真实输出一致",
          bool(quoted) and all(q == real_head for q in quoted),
          (quoted[:1], real_head))

    return finish()


def finish():
    ok = sum(1 for _, c, _ in results if c)
    for name, cond, detail in results:
        print(("PASS  " if cond else "FAIL  ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    print("\n%d/%d 通过" % (ok, len(results)))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
