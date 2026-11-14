#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配额胶囊技能的输出层：把 quota_watch 的报告排成 Markdown。

设计要点：
- 数据逻辑不在这里重复实现，全部来自同目录的 quota_watch.py（与主项目同源）。
- 有缓存：按「日志文件集合 + mtime + 大小」签名，命中且 300 秒内直接复用。
- 输出自带取数耗时与数据新鲜度，用户一眼能判断数据是否是新的。

用法：
    python quota_report.py            # Markdown 表格
    python quota_report.py --json     # 原始 JSON
    python quota_report.py --no-cache # 强制重扫
"""
import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import quota_watch as qw  # noqa: E402  同源数据层
import phrasing  # noqa: E402  与通知共用同一句文案

CACHE_TTL = 300.0
WINDOW_MIN = 60


def cache_file():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "quota-pill")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return os.path.join(d, "skill-cache.json")


def log_signature():
    """文件集合 + 纳秒级 mtime + 大小。

    用 st_mtime_ns 而不是 st_mtime：float 秒在 1.7e9 量级只剩约 0.1 微秒精度，
    同一秒内的两次追加可能被抹平。实测：自然连写不会漏，但若 mtime 与 size
    被强制成完全相同（如等长覆盖并保留时间戳），签名会误判为同一份数据。
    日志是追加写，size 必变，所以实际不受影响；提高精度只是把边界推远。
    """
    parts = []
    for fp in glob.glob(os.path.join(qw.PROJECTS, "*", "*.jsonl")):
        try:
            st = os.stat(fp)
        except OSError:
            continue
        parts.append([os.path.basename(fp), st.st_mtime_ns, st.st_size])
    parts.sort()
    return parts


def load_report(use_cache=True):
    """返回 (report, 是否命中缓存, 取数秒数)。"""
    t0 = time.perf_counter()
    path = cache_file()
    if use_cache and path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            if (blob.get("sig") == log_signature()
                    and time.time() - blob.get("at", 0) < CACHE_TTL):
                return blob["report"], True, time.perf_counter() - t0
        except (OSError, ValueError, KeyError):
            pass

    rep = qw.build_report(WINDOW_MIN, 3.0)
    cost = time.perf_counter() - t0
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"sig": log_signature(), "at": time.time(),
                           "report": rep}, f, ensure_ascii=False)
        except OSError:
            pass
    return rep, False, cost


def fmt_age(ts):
    if not ts:
        return "—"
    sec = max(0.0, time.time() - ts)
    if sec < 90:
        return "%d 秒前" % int(sec)
    if sec < 5400:
        return "%d 分钟前" % int(sec / 60)
    return "%.1f 小时前" % (sec / 3600.0)


def fmt_eta(m):
    """触限预测。上游对低置信度样本会主动给出 None，这里要说清原因而不是留空。"""
    eta = m.get("eta_hours_to_limit")
    if eta is None:
        if m.get("rate_pct_per_hour"):
            return "暂不预测"
        return "—"
    if eta > 48:
        return "> 48 小时"
    return "%.1f 小时后" % eta


CONF = {"high": "高", "medium": "中", "low": "低", "idle": "无消耗", "none": "—"}


def render(rep, cached, cost):
    models = [m for m in rep.get("models", []) if not m.get("stale")]
    if rep.get("error") or not models:
        return "没有找到本周期内的配额记录。\n\n%s" % (
            rep.get("error") or "日志里没有带 quota 的行，先正常对话一轮。")

    lines = [
        "| 模型 | 已用 | 本周期重置 | 增速 | 预计触限 | 可信度 | 数据新鲜度 |",
        "|---|---:|---|---:|---|---|---|",
    ]
    for m in models:
        rate = "%.1f%%/h" % m["rate_pct_per_hour"] if m.get("rate_pct_per_hour") else "—"
        lines.append("| `%s` | %g%% | %s | %s | %s | %s | %s |" % (
            m["model"], m["percent_used"], m.get("reset_local") or "—",
            rate, fmt_eta(m),
            CONF.get(m.get("rate_confidence"), "—"),
            fmt_age(m.get("last_seen_ts"))))

    stale = len(rep.get("models", [])) - len(models)
    tail = [
        "",
        "合计 %d 个模型%s · 取数 %.2f 秒（%s） · 日志目录 `%s`" % (
            len(models),
            "（另有 %d 个停在上一周期，未计入）" % stale if stale else "",
            cost, "命中缓存" if cached else "重新扫描", qw.HOME),
    ]
    risk = [m for m in models if m.get("level") == "critical"]
    if risk:
        tail.append("")
        tail.append("**注意**：%s。" % "；".join(phrasing.line(m) for m in risk))
    return "\n".join(lines + tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    rep, cached, cost = load_report(use_cache=not args.no_cache)
    if args.json:
        print(json.dumps({"cached": cached, "cost_s": round(cost, 3), "report": rep},
                         ensure_ascii=False, indent=2))
        return 0
    print(render(rep, cached, cost))
    return 1 if rep.get("has_risk") else 0


if __name__ == "__main__":
    sys.exit(main())
