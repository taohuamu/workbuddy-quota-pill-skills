#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查技能里内置的 quota_watch.py 是否与主项目同源。

技能必须自包含，所以数据层需要一份副本；副本一旦与上游脱节，
技能给出的数字就会和桌面版不一致。本脚本用哈希兜住这件事。

同时校验 references/ 的「上次核对」日期：那份文件里写着的日期是它唯一的
时效凭据，内容改了却忘改日期，读者会以为结论还停在旧日期。

用法：
    python sync_check.py                    # 默认对比同级主项目
    python sync_check.py --upstream <path>  # 指定上游文件
    python sync_check.py --fix              # 用上游覆盖副本

退出码：0 一致；1 不一致（需要同步）；2 找不到上游
"""
import argparse
import datetime as dt
import hashlib
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UPSTREAM = os.path.abspath(
    os.path.join(HERE, "..", "..", "..", "workbuddy-quota-pill", "quota_watch.py"))
LOCAL = os.path.join(HERE, "quota_watch.py")
FORECAST_LOCAL = os.path.join(HERE, "forecast.py")
REFERENCES = os.path.abspath(os.path.join(HERE, "..", "references"))

DATE_RE = re.compile(r"上次核对[：:]\s*(\d{4}-\d{2}-\d{2})")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_reference_dates():
    """日期早于文件最后修改日期 → 内容改过但没更新日期。返回提醒列表。"""
    if not os.path.isdir(REFERENCES):
        return []
    problems = []
    for name in sorted(os.listdir(REFERENCES)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(REFERENCES, name)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        m = DATE_RE.search(text)
        if not m:
            continue
        claimed = m.group(1)
        mtime = dt.date.fromtimestamp(os.path.getmtime(path))
        try:
            claimed_date = dt.datetime.strptime(claimed, "%Y-%m-%d").date()
        except ValueError:
            problems.append("%s：日期无法解析（%s）" % (name, claimed))
            continue
        if claimed_date < mtime:
            problems.append("%s：内容改于 %s，头部仍写 %s" % (name, mtime, claimed))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    code = 0
    # 数据层两份：算数的是 quota_watch，判预测的是 forecast。两个都必须同源，
    # 否则技能版与桌面版会对同一个状态给出两个结论。
    pairs = [
        ("quota_watch.py", args.upstream, LOCAL),
        ("forecast.py", os.path.join(os.path.dirname(args.upstream), "forecast.py"),
         FORECAST_LOCAL),
    ]
    for name, upstream, local in pairs:
        if not os.path.exists(upstream):
            print("%s：找不到上游文件 %s" % (name, upstream))
            print("  技能副本仍在，但无法判断是否同源。")
            code = max(code, 2)
            continue
        up, lo = digest(upstream), digest(local)
        if up == lo:
            print("同源 OK  %-14s %s" % (name, lo[:16]))
            continue
        print("不同源：%-14s 上游 %s / 副本 %s" % (name, up[:16], lo[:16]))
        if args.fix:
            shutil.copyfile(upstream, local)
            print("  已用上游覆盖副本，新哈希 %s" % digest(local)[:16])
        else:
            print("  执行 `python sync_check.py --fix` 同步，或先确认上游改动是否该进技能。")
            code = max(code, 1)

    stale = check_reference_dates()
    if stale:
        print("\nreferences 时效提醒（不阻断）：")
        for line in stale:
            print("  - " + line)
        print("  改了内容就把「上次核对」日期一并改掉。")
    else:
        print("references 日期 OK")

    return code


if __name__ == "__main__":
    sys.exit(main())
