"""原始色谱强度采样的峰面积积分（纯函数，全部使用精确有理数运算）。

输入为 5～500 个 ``{time_ms, intensity}`` 原始采样点（时间严格递增、强度非负）、
积分起止下标与 2～60 个严格递增的峰顶下标。相邻峰顶之间以强度最低的内部采样点
（并列取最早下标）作为共用分界（谷点）。每段以两端采样点连线作基线，逐点将
强度减去基线并截为非负，再按实际时间间隔做梯形积分。每段面积返回约分分数；
另取全部面积分母的最小公倍数作为统一倍数，放大后给出整数峰面积数组。
"""

from __future__ import annotations

from fractions import Fraction
from math import lcm
from typing import Any


class IntegrationError(ValueError):
    """输入不满足业务规则，API 层映射为 HTTP 422。"""


def _frac(value: Fraction) -> dict[str, int]:
    """把约分有理数序列化为 {n, d}，分母恒为正。"""
    return {"n": value.numerator, "d": value.denominator}


def integrate_peaks(
    samples: list[dict[str, Any]],
    start_index: int,
    end_index: int,
    peak_indices: list[int],
) -> dict[str, Any]:
    """峰面积积分主流程，返回可直接序列化的结果字典。"""
    n = len(samples)
    if not 5 <= n <= 500:
        raise IntegrationError("samples must contain 5 to 500 points")
    if not 2 <= len(peak_indices) <= 60:
        raise IntegrationError("peak_indices must contain 2 to 60 entries")

    times = [s["time_ms"] for s in samples]
    intensities = [s["intensity"] for s in samples]
    if any(times[i] >= times[i + 1] for i in range(n - 1)):
        raise IntegrationError("sample times must be strictly increasing")
    if any(v < 0 for v in intensities):
        raise IntegrationError("sample intensities must be non-negative")

    if not 0 <= start_index < n:
        raise IntegrationError(f"start_index out of range [0, {n - 1}]")
    if not 0 <= end_index < n:
        raise IntegrationError(f"end_index out of range [0, {n - 1}]")
    if start_index >= end_index:
        raise IntegrationError("start_index must be strictly less than end_index")

    for pos, idx in enumerate(peak_indices):
        if not 0 <= idx < n:
            raise IntegrationError(
                f"peak_indices[{pos}] out of range [0, {n - 1}]"
            )
    for pos in range(len(peak_indices) - 1):
        a, b = peak_indices[pos], peak_indices[pos + 1]
        if a >= b:
            raise IntegrationError("peak_indices must be strictly increasing")
        if b - a < 2:
            # 两峰顶之间至少要有一个内部采样点，谷点才有候选
            raise IntegrationError(
                "adjacent peak apexes must have at least one interior sample "
                "between them"
            )

    # 峰顶必须严格位于起止下标之间（峰顶下标严格递增，只需检查首尾）
    if not (start_index < peak_indices[0] and peak_indices[-1] < end_index):
        raise IntegrationError(
            "peak apexes must lie strictly between start_index and end_index"
        )

    # —— 谷点分界：相邻峰顶之间的内部点中强度最低者，并列取最早下标 ——
    boundaries = [start_index]
    for pos in range(len(peak_indices) - 1):
        lo, hi = peak_indices[pos], peak_indices[pos + 1]
        valley = min(
            range(lo + 1, hi),
            key=lambda i: (intensities[i], i),
        )
        boundaries.append(valley)
    boundaries.append(end_index)

    segments_out: list[dict[str, Any]] = []
    areas: list[Fraction] = []

    for k, apex in enumerate(peak_indices):
        b0, b1 = boundaries[k], boundaries[k + 1]
        t0, t1 = times[b0], times[b1]
        i0, i1 = intensities[b0], intensities[b1]
        span = t1 - t0  # 时间严格递增 => 恒正

        # 两端连线基线在各采样时刻的取值；减基线后截为非负
        corrected: list[Fraction] = []
        for i in range(b0, b1 + 1):
            baseline = i0 + Fraction((i1 - i0) * (times[i] - t0), span)
            height = Fraction(intensities[i]) - baseline
            corrected.append(height if height > 0 else Fraction(0))

        # 按实际时间间隔精确梯形积分
        area = Fraction(0)
        for j in range(b1 - b0):
            dt = times[b0 + j + 1] - times[b0 + j]
            area += (corrected[j] + corrected[j + 1]) * dt / 2

        segments_out.append(
            {
                "start_index": b0,
                "end_index": b1,
                "start_time_ms": t0,
                "end_time_ms": t1,
                "peak_index": apex,
                "peak_time_ms": times[apex],
                "area": _frac(area),
            }
        )
        areas.append(area)

    # 用全部面积分母的最小公倍数统一放大为整数（零面积保留）
    multiplier = lcm(*(a.denominator for a in areas))
    peaks_out: list[dict[str, int]] = []
    for apex, area in zip(peak_indices, areas):
        scaled = area * multiplier
        assert scaled.denominator == 1  # multiplier 为各分母公倍数
        peaks_out.append({"time_ms": times[apex], "area": scaled.numerator})
    # 峰顶下标严格递增且采样时间严格递增，故 peaks 已按峰顶时间排序

    return {
        "segments": segments_out,
        "multiplier": multiplier,
        "peaks": peaks_out,
    }
