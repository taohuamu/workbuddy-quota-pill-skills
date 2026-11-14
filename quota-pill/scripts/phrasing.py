#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把判定结论翻成给人看的一句话。

报告的命令行提示和系统通知都从这里取句子。分两处各写一套的话，同一个状态会在
报告里说「按最坏打算」、在通知里说「接近上限」——用户看到的是两套话。

数据层的 `verdict` 是给表格用的完整句（"重置前就会耗尽"这种在表里有位置放下），
这里统一换成「多久触限」一个口径：说得出时间就带时间，说不出就说即将触限，
撑得到重置就说额度充足。只换说法，不改判定——判据永远来自 quota_watch。
"""
import quota_watch as qw

# 只登记确实要换说法的几种。没登记的按原样输出：宁可长一点，也别猜错意思。
VERDICT_TEXT = {
    # 95% 以上，说「随时」比编一个零点几小时更诚实
    "已到上限，随时会被拒": "即将触限",
    "重置前就会耗尽": "即将触限",     # 兜底：算不出时间时才落到这句
    "按当前节奏够用": "剩余额度充足",
}


def _within(hours):
    """「4.2 小时内触限」。整点小时去掉 .0，让「3 小时内」不被写成「3.0 小时内」。"""
    return "%s内触限" % qw.fmt_dur(hours).replace(".0 小时", " 小时")


def conclusion(m):
    """结论文案。m 是 quota_watch 产出的模型字典。"""
    tail = (m.get("verdict") or "").strip()
    if tail.startswith("已用"):
        # 低置信度那条把百分比写在句首（"已用 82%，样本太短…"）。百分比由 line()
        # 统一加，这里剥掉，否则会拼成「已用 82%，已用 82%」。
        tail = tail.partition("，")[2].strip()
    if "无法预测" in tail:
        return "样本不足，无法预测触限时间"
    # 「撑不到重置」和「X 小时内触限」说的是同一件事，差别只在有没有给时间。
    # 有 eta 就统一按「多久」说，顺手把「3.0 小时」写成「3 小时」——
    # 25% 已用配「即将触限」会让人以为马上就没了，其实还有几个小时。
    eta = m.get("eta_hours_to_limit")
    if eta and (tail == "重置前就会耗尽" or tail.endswith("内触限")):
        return _within(eta)
    return VERDICT_TEXT.get(tail, tail or "接近上限")


def line(m):
    """「模型 已用 N%，结论」——报告与通知共用这一句。"""
    return "%s 已用 %d%%，%s" % (
        m["model"], int(round(m["percent_used"])), conclusion(m))
