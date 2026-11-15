#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forecast.py 的行为测试：观测、判定、读数、文案四条线。

覆盖的是「换成净增格数之后，判定与读数会不会走偏」，不重复数据层（那由主项目
的 tests/test_core.py 负责）。

运行：python tools/test_forecast.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "quota-pill", "scripts")
sys.path.insert(0, SCRIPTS)

import forecast as fc  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def series(start_p, per_min, minutes, step=1.0, t0=0.0):
    """每 step 分钟涨 per_min*step 格，返回 [(ts, percent)]。"""
    out = []
    t = 0.0
    p = float(start_p)
    while t <= minutes:
        out.append((t0 + t * 60, p))
        t += step
        p += per_min * step / 60.0
    return out


def main():
    ok = fc._selftest() == 0
    check("内置自检全过", ok)

    # 观测：回退不算负贡献
    s = [(0, 50), (60, 51), (120, 50), (180, 52)]
    check("裸计数把回退记 0", fc.grids_in(s, -1, 200)[0] == 3)
    check("复合跳变退化为事件数", fc.cells_of(s, -1, 200)[0] == 2)

    # 判定：快→提醒，慢→不提醒
    fast = series(60, 48, 13)          # 48 格/小时，p 60→70
    r = fc.decide(fast, hours_to_reset=10)
    check("48 格/小时能提前提醒", r["alert"] is True, r)
    slow = series(60, 4, 13)           # 4 格/小时
    check("4 格/小时不提醒", fc.decide(slow, hours_to_reset=10)["alert"] is False)

    # 地板：p<55 一律不提醒
    low = series(20, 60, 20)
    check("低于地板不提醒", fc.decide(low, hours_to_reset=10)["alert"] is False)

    # 让位：p>=80 交给百分比条件
    high = series(80, 30, 10)
    check("p>=80 让位", fc.decide(high, hours_to_reset=10)["alert"] is False)

    # 读数：k=0 不给时间
    flat = [(0, 50), (3600, 50)]
    r0 = fc.decide(flat, hours_to_reset=10)
    check("k=0 → idle", r0["tier"] == "idle")
    check("k=0 不给时间", r0["eta_min"] is None)
    check("k=0 文案是事实", fc.phrase(r0) == "近 15 分钟无新增", fc.phrase(r0))

    # 文案里的窗口必须跟着 --window 走（D2 的 B4：改 45 分钟仍说 15 分钟）
    s45 = [(0.0, 50.0), (60.0, 50.0)]
    d45 = fc.decide(s45, now=120.0, window_min=45)
    check("decide 把窗口带进结果", d45.get("window_min") == 45.0, d45.get("window_min"))
    check("窗口 45 时文案说 45 分钟", fc.phrase(d45) == "近 45 分钟无新增", fc.phrase(d45))
    check("不传参也能拿到正确窗口", fc.phrase(fc.decide(s45, now=120.0, window_min=45))
          == "近 45 分钟无新增")

    # 越界窗口：0 / 负数夹到 1，且文案不能出现「近 0 分钟」「近 -5 分钟」
    d0 = fc.decide(s45, now=120.0, window_min=0)
    check("窗口 0 夹到 1", d0["window_min"] == 1.0, d0.get("window_min"))
    check("窗口 0 的文案不出现 0 分钟", "近 1 分钟无新增" == fc.phrase(d0), fc.phrase(d0))
    dn = fc.decide(s45, now=120.0, window_min=-5)
    check("负窗口也夹到 1", dn["window_min"] == 1.0, dn.get("window_min"))

    # 读数：中位时间随 k 单调下降
    meds = []
    for k in (1, 3, 6, 12):
        sp = series(71, k * 4, 15)    # 15 分钟内涨 k 格
        meds.append(fc.decide(sp, hours_to_reset=99)["eta_min"])
    check("k 越大中位时间越短", all(a > b for a, b in zip(meds, meds[1:])), meds)

    # 区间的方向：5% 分位 < 中位 < 95% 分位
    q5, q50, q95 = (fc.t_quantile(q, 29, 9) for q in (0.05, 0.5, 0.95))
    check("分位有序", q5 < q50 < q95, (q5, q50, q95))
    check("p=71 k=9 中位≈47 分钟", 45 <= q50 <= 49, q50)

    # 封顶：中位晚于重置
    capped = fc.decide(series(70, 4, 15), hours_to_reset=1)
    check("中位晚于重置 → capped", capped["capped"] is True, capped)
    check("封顶文案", "本周期内" in fc.phrase(capped), fc.phrase(capped))

    # 文案：只给结果
    txt = fc.say("m", 84, {"tier": "ok", "eta_min": 40, "capped": False})
    check("正文不含格数", "格" not in txt, txt)
    check("正文不含速率", "/小时" not in txt, txt)
    check("正文不含「小时内触限」", "小时内触限" not in txt, txt)
    check("正文带结果", "约 40 分钟后到上限" in txt, txt)

    # 等级只看百分比
    check("level 81 → warn", fc.level_of(81) == "warn")
    check("level 95 → critical", fc.level_of(95) == "critical")
    check("level 40 → ok", fc.level_of(40) == "ok")

    # 表格列
    check("观测列", fc.obs_cell({"k": 4}) == "涨 4%")
    check("观测列零增量照实写", fc.obs_cell({"k": 0}) == "涨 0%")
    check("观测列不用内部单位「格」", "格" not in fc.obs_cell({"k": 4}))

    # 重置前不足一个窗口：不能写成「数据不足」（快照是全的，只是周期快结束）
    s_soon = series(90, 1, 30)
    d_soon = fc.decide(s_soon, window_min=15, hours_to_reset=0.05)
    check("距重置不足窗口 → tier=soon", d_soon["tier"] == "soon", d_soon)
    check("soon 说「即将重置」", fc.phrase(d_soon) == "即将重置", fc.phrase(d_soon))
    check("soon 的观测列留空", fc.obs_cell(d_soon) == "—", fc.obs_cell(d_soon))
    check("soon 的时长列说「即将重置」", fc.eta_cell(d_soon) == "即将重置",
          fc.eta_cell(d_soon))
    check("soon 不触发提醒", d_soon["alert"] is False)

    # 接线：forecast.py 必须进 runtime 副本清单
    import install_task
    check("STAGE_FILES 含 forecast.py", "forecast.py" in install_task.STAGE_FILES,
          install_task.STAGE_FILES)

    ok_n = sum(1 for _, c, _ in results if c)
    for name, cond, detail in results:
        print(("PASS  " if cond else "FAIL  ") + name +
              (("  [" + str(detail) + "]") if detail and not cond else ""))
    print("\n%d/%d 通过" % (ok_n, len(results)))
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
