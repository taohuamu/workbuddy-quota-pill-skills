#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把判定结论翻成给人看的一句话。

报告的命令行提示和系统通知都从这里取句子。分两处各写一套的话，同一个状态会在
报告里说「按最坏打算」、在通知里说「接近上限」——用户看到的是两套话。

0.5.0 起主句由 `forecast.phrase()` 给（「按此速度约 40 分钟后到上限」/「近 15 分钟无新增」），
本文件只做两件事：给它补上「模型 已用 N%」的前缀；以及在**没有 forecast** 时（例如停在
上一周期的模型）把数据层的 `verdict` 翻成人话。只换说法，不改判定。
"""
import quota_watch as qw
import forecast


def _within(hours):
    """「4.2 小时内触限」。整点小时去掉 .0，让「3 小时内」不被写成「3.0 小时内」。"""
    return "%s内触限" % qw.fmt_dur(hours).replace(".0 小时", " 小时")


def conclusion(m, high_pct=80.0):
    """结论文案。m 是 quota_watch 产出的模型字典。

    有 forecast 就用它的结果句（「按此速度约 40 分钟后到上限」/「近 15 分钟无新增」）。
    下面这几个分支只在没有 forecast 时兜底——例如停在上一周期的模型。

    high_pct 与 notify.py 的 --pct 保持一致：达到这个百分比就会被提醒，所以
    「按当前节奏够用」在这条线以上不能说成「额度充足」——一边提醒一边说充足，
    读的人只会觉得文案在敷衍。
    """
    fc = m.get("forecast")
    if fc is not None:
        return forecast.phrase(fc)
    tail = (m.get("verdict") or "").strip()
    if tail.startswith("已用"):
        # 低置信度那条把百分比写在句首（"已用 82%，样本太短…"）。百分比由 line()
        # 统一加，这里剥掉，否则会拼成「已用 82%，已用 82%」。
        tail = tail.partition("，")[2].strip()
    if "无法预测" in tail:
        return "样本不足，无法预测触限时间"
    if tail == "按当前节奏够用":
        return ("用量偏高，暂无触限风险"
                if (m.get("percent_used") or 0) >= high_pct else "剩余额度充足")
    # 「撑不到重置」和「X 小时内触限」说的是同一件事，差别只在有没有给时间。
    # 有 eta 就统一按「多久」说，顺手把「3.0 小时」写成「3 小时」；没有 eta 只说即将触限。
    eta = m.get("eta_hours_to_limit")
    if tail.endswith("内触限") or tail == "重置前就会耗尽":
        return _within(eta) if eta else "即将触限"
    if tail.startswith("已到上限"):
        return "即将触限"
    # 没登记的按原样输出：宁可长一点，也别猜错意思。
    return tail or "接近上限"


def line(m, high_pct=80.0):
    """「模型 已用 N%，结论」——报告与通知共用这一句。"""
    return "%s 已用 %d%%，%s" % (
        m["model"], int(round(m["percent_used"])), conclusion(m, high_pct))
