"""峰面积积分纯函数测试（手算固定边界用例）。"""

from __future__ import annotations

import pytest

from app.integration import IntegrationError, integrate_peaks


def S(times_intensities):
    return [
        {"time_ms": t, "intensity": i} for t, i in times_intensities
    ]


def test_two_peaks_uneven_times_fractional_areas():
    # 时间等距、两端点强度为 0：谷点 idx5(int=4)。
    # 段 1 [0,5] 基线斜率 4/5；段 2 [5,9] 基线斜率 6/5。
    samples = S(
        [
            (0, 0), (1, 0), (2, 10), (3, 6), (4, 5),
            (5, 4), (6, 5), (8, 20), (9, 5), (10, 10),
        ]
    )
    r = integrate_peaks(samples, 0, 9, [2, 7])

    seg0, seg1 = r["segments"]
    assert (seg0["start_index"], seg0["end_index"]) == (0, 5)
    assert (seg0["start_time_ms"], seg0["end_time_ms"]) == (0, 5)
    assert seg0["peak_index"] == 2
    assert seg0["peak_time_ms"] == 2
    assert seg0["area"] == {"n": 69, "d": 5}

    assert (seg1["start_index"], seg1["end_index"]) == (5, 9)
    assert (seg1["start_time_ms"], seg1["end_time_ms"]) == (5, 10)
    assert seg1["peak_index"] == 7
    assert seg1["area"] == {"n": 93, "d": 5}

    # 统一倍数为各面积分母的 LCM；整数峰按峰顶时间升序
    assert r["multiplier"] == 5
    assert r["peaks"] == [
        {"time_ms": 2, "area": 69},
        {"time_ms": 8, "area": 93},
    ]


def test_three_peaks_uneven_times_halves():
    # 非等距时间产生半整数：17/2、26、30；倍数 2 -> 17、52、60。
    samples = S(
        [
            (0, 0), (1, 0), (2, 0), (3, 10), (4, 2),
            (5, 4), (6, 5), (7, 20), (8, 5), (9, 2),
            (10, 4), (11, 8), (12, 16), (13, 6), (14, 1),
            (15, 0),
        ]
    )
    r = integrate_peaks(samples, 0, 15, [3, 7, 12])
    assert [s["area"] for s in r["segments"]] == [
        {"n": 17, "d": 2},
        {"n": 26, "d": 1},
        {"n": 30, "d": 1},
    ]
    # 谷点：峰顶 3、7 之间最低为 idx4(int=2)；峰顶 7、12 之间最低为 idx9(int=2)
    assert [(s["start_index"], s["end_index"]) for s in r["segments"]] == [
        (0, 4), (4, 9), (9, 15)
    ]
    assert r["multiplier"] == 2
    assert r["peaks"] == [
        {"time_ms": 3, "area": 17},
        {"time_ms": 7, "area": 52},
        {"time_ms": 12, "area": 60},
    ]


def test_baseline_above_interior_is_clipped_to_zero():
    # 谷底平台：连线基线在平台内部高于强度，逐点截为非负。
    # 第一段 idx1 处基线 5/3 > 强度 0，该梯形截为 0（不产生负值）。
    samples = S(
        [(0, 0), (3, 0), (6, 10), (9, 5), (12, 5), (15, 20), (18, 0)]
    )
    r = integrate_peaks(samples, 0, 6, [2, 5])
    assert [s["area"] for s in r["segments"]] == [
        {"n": 20, "d": 1},
        {"n": 60, "d": 1},
    ]
    assert r["multiplier"] == 1
    assert r["peaks"] == [
        {"time_ms": 6, "area": 20},
        {"time_ms": 15, "area": 60},
    ]


def test_tied_valley_picks_earliest_index():
    # idx3、idx4 强度并列最低（均为 4），取最早 idx3 为共用分界。
    samples = S([(0, 0), (1, 0), (2, 10), (3, 4), (4, 4), (5, 10), (6, 0)])
    r = integrate_peaks(samples, 0, 6, [2, 5])
    assert [(s["start_index"], s["end_index"]) for s in r["segments"]] == [
        (0, 3), (3, 6)
    ]
    assert [s["area"] for s in r["segments"]] == [
        {"n": 22, "d": 3},
        {"n": 10, "d": 1},
    ]
    assert r["multiplier"] == 3
    assert r["peaks"] == [
        {"time_ms": 2, "area": 22},
        {"time_ms": 5, "area": 30},
    ]


def test_zero_area_peak_is_retained():
    # 中间峰顶强度 1 恰好落在谷点 idx2/idx4（均为 1）的连线基线上，
    # 整段截后全为 0；零面积在整数峰数组中保留。
    samples = S(
        [(0, 0), (1, 10), (2, 1), (3, 1), (4, 1), (5, 10), (6, 0)]
    )
    r = integrate_peaks(samples, 0, 6, [1, 3, 5])
    assert [(s["start_index"], s["end_index"]) for s in r["segments"]] == [
        (0, 2), (2, 4), (4, 6)
    ]
    assert [s["area"] for s in r["segments"]] == [
        {"n": 19, "d": 2},
        {"n": 0, "d": 1},
        {"n": 19, "d": 2},
    ]
    assert r["multiplier"] == 2
    assert r["peaks"] == [
        {"time_ms": 1, "area": 19},
        {"time_ms": 3, "area": 0},
        {"time_ms": 5, "area": 19},
    ]


def test_minimum_and_maximum_sample_counts_valid():
    # 5 个点、2 个峰顶（峰顶 1 与 3 之间恰有一个内部点 idx2）
    samples = S([(0, 0), (1, 5), (2, 1), (3, 5), (4, 0)])
    r = integrate_peaks(samples, 0, 4, [1, 3])
    assert r["multiplier"] == 2
    assert r["peaks"] == [
        {"time_ms": 1, "area": 9},
        {"time_ms": 3, "area": 9},
    ]


def test_exact_timing_uses_actual_intervals():
    # 同样的强度序列，拉伸时间间隔后面积按实际间隔变化。
    base = S([(0, 0), (1, 5), (2, 1), (3, 5), (4, 0)])
    wide = S([(0, 0), (10, 5), (20, 1), (30, 5), (40, 0)])
    rb = integrate_peaks(base, 0, 4, [1, 3])
    rw = integrate_peaks(wide, 0, 4, [1, 3])
    assert rb["segments"][0]["area"] == {"n": 9, "d": 2}
    assert rw["segments"][0]["area"] == {"n": 45, "d": 1}


# —— 非法输入 ——

def _samples_n(n):
    return S((i, i % 3) for i in range(n))


def test_422_sample_count_out_of_range():
    with pytest.raises(IntegrationError, match="5 to 500"):
        integrate_peaks(_samples_n(4), 0, 3, [1, 2])
    with pytest.raises(IntegrationError, match="5 to 500"):
        integrate_peaks(_samples_n(501), 0, 500, [100, 200])


def test_422_peak_count_out_of_range():
    samples = _samples_n(10)
    with pytest.raises(IntegrationError, match="2 to 60"):
        integrate_peaks(samples, 0, 9, [2])
    # 61 个峰顶但只有 8 个可用内部位置，先在峰顶间距校验处失败
    with pytest.raises(IntegrationError):
        integrate_peaks(samples, 0, 9, list(range(61)))


def test_422_times_not_strictly_increasing():
    samples = S([(0, 0), (1, 0), (1, 5), (3, 0), (4, 0)])
    with pytest.raises(IntegrationError, match="strictly increasing"):
        integrate_peaks(samples, 0, 4, [1, 3])


def test_422_negative_intensity():
    samples = S([(0, 0), (1, 0), (2, -1), (3, 0), (4, 0)])
    with pytest.raises(IntegrationError, match="non-negative"):
        integrate_peaks(samples, 0, 4, [1, 3])


def test_422_index_out_of_range():
    samples = _samples_n(5)
    with pytest.raises(IntegrationError, match="start_index"):
        integrate_peaks(samples, -1, 4, [1, 3])
    with pytest.raises(IntegrationError, match="end_index"):
        integrate_peaks(samples, 0, 5, [1, 3])
    with pytest.raises(IntegrationError, match=r"peak_indices\[1\]"):
        integrate_peaks(samples, 0, 4, [1, 9])


def test_422_start_not_before_end():
    samples = _samples_n(5)
    with pytest.raises(IntegrationError, match="strictly less"):
        integrate_peaks(samples, 3, 3, [1, 4])
    with pytest.raises(IntegrationError, match="strictly less"):
        integrate_peaks(samples, 4, 1, [2, 3])


def test_422_peak_indices_not_strictly_increasing():
    samples = _samples_n(10)
    with pytest.raises(IntegrationError, match="strictly increasing"):
        integrate_peaks(samples, 0, 9, [2, 2])
    with pytest.raises(IntegrationError, match="strictly increasing"):
        integrate_peaks(samples, 0, 9, [5, 3])


def test_422_apex_without_interior_between():
    samples = _samples_n(10)
    # 相邻峰顶下标差 1，中间无内部采样点
    with pytest.raises(IntegrationError, match="interior sample"):
        integrate_peaks(samples, 0, 9, [3, 4, 6])


def test_422_apex_outside_start_end():
    samples = _samples_n(10)
    # 峰顶必须严格位于起止之间
    with pytest.raises(IntegrationError, match="strictly between"):
        integrate_peaks(samples, 2, 8, [2, 6])
    with pytest.raises(IntegrationError, match="strictly between"):
        integrate_peaks(samples, 2, 6, [3, 6])


def test_segments_share_valley_and_partition_range():
    samples = S(
        [
            (0, 0), (1, 0), (2, 0), (3, 10), (4, 2),
            (5, 4), (6, 5), (7, 20), (8, 5), (9, 2),
            (10, 4), (11, 8), (12, 16), (13, 6), (14, 1),
            (15, 0),
        ]
    )
    r = integrate_peaks(samples, 0, 15, [3, 7, 12])
    bounds = [r["segments"][0]["start_index"]] + [
        s["end_index"] for s in r["segments"]
    ]
    assert bounds == [0, 4, 9, 15]
    # 每个峰顶严格位于本段内部
    for s in r["segments"]:
        assert s["start_index"] < s["peak_index"] < s["end_index"]


def test_random_instances_agree_with_independent_reference():
    # 200 组随机实例，与一份独立的朴素实现对拍：
    # 谷点选取、分段、基线截断、梯形面积、LCM 放大、排序全部一致。
    import random
    from fractions import Fraction as F
    from math import lcm

    rng = random.Random(20260929)
    for _ in range(200):
        n = rng.randint(5, 60)
        t = 0
        times, intens = [], []
        for _i in range(n):
            t += rng.randint(1, 7)
            times.append(t)
            intens.append(rng.randint(0, 20))

        # 峰顶间距 ≥ 2、严格位于 0 与 n-1 之间
        k = rng.randint(2, min(20, (n - 1) // 2 + 1))
        domain = list(range(1, n - 1, 2))  # 天然间距 2
        rng.shuffle(domain)
        apex = sorted(domain[:k])

        samples = S(zip(times, intens))
        got = integrate_peaks(samples, 0, n - 1, apex)

        # —— 独立参考实现 ——
        bounds = [0]
        for a, b in zip(apex, apex[1:]):
            valley = min(range(a + 1, b), key=lambda i: (intens[i], i))
            bounds.append(valley)
        bounds.append(n - 1)

        ref_areas = []
        for s_i, (b0, b1) in enumerate(zip(bounds, bounds[1:])):
            area = F(0)
            for j in range(b0, b1):
                dt = times[j + 1] - times[j]
                heights = []
                for i in (j, j + 1):
                    base = intens[b0] + F(
                        (intens[b1] - intens[b0]) * (times[i] - times[b0]),
                        times[b1] - times[b0],
                    )
                    heights.append(max(F(0), F(intens[i]) - base))
                area += (heights[0] + heights[1]) * dt / 2
            ref_areas.append(area)

        mult = lcm(*(a.denominator for a in ref_areas))
        assert got["multiplier"] == mult
        assert [s["area"] for s in got["segments"]] == [
            {"n": a.numerator, "d": a.denominator} for a in ref_areas
        ]
        assert got["peaks"] == [
            {"time_ms": times[a], "area": (ar * mult).numerator}
            for a, ar in zip(apex, ref_areas)
        ]
        for seg, b0, b1 in zip(got["segments"], bounds, bounds[1:]):
            assert seg["start_index"] == b0
            assert seg["end_index"] == b1
            assert seg["start_time_ms"] == times[b0]
            assert seg["end_time_ms"] == times[b1]
