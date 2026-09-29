"""请求/响应 Pydantic 模型。

严格类型：布尔值不会被当作整数，浮点不会被静默截断为整数，
类型层拒绝统一产生 HTTP 422。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, StrictInt, StrictStr


class ReferencePeak(BaseModel):
    id: StrictStr
    time_ms: StrictInt


class AssignRequest(BaseModel):
    reference_peaks: list[ReferencePeak] = Field(min_length=2, max_length=40)
    measured_times_ms: list[StrictInt] = Field(min_length=2, max_length=60)
    is_ref_id_1: StrictStr
    is_meas_idx_1: StrictInt
    is_ref_id_2: StrictStr
    is_meas_idx_2: StrictInt
    tolerance_ms: StrictInt = Field(ge=0)


class FractionOut(BaseModel):
    n: int  # 约分后的分子（可负）
    d: int  # 约分后的分母（恒正）


class MatchOut(BaseModel):
    ref_id: str
    ref_index: int
    meas_index: int
    calibrated_time_ms: FractionOut
    signed_deviation_ms: FractionOut  # 校准值 - 参考值


class AssignResponse(BaseModel):
    # 与参考峰输入顺序一一对应：配对给出实测下标，否则 null
    assignments: list[int | None]
    unpaired_meas_indices: list[int]
    matches: list[MatchOut]


# ---------------------------------------------------------------------------
# 标准加入法（POST /v1/standard-addition）
# ---------------------------------------------------------------------------

class MeasuredPeak(BaseModel):
    time_ms: StrictInt
    area: StrictInt = Field(ge=0)


class Injection(BaseModel):
    # 非负整数加标浓度
    added_concentration: StrictInt = Field(ge=0)
    # 按采集顺序排列的实测峰
    measured_peaks: list[MeasuredPeak] = Field(min_length=2, max_length=60)
    # 两枚内标在 measured_peaks 中的下标
    is_meas_idx_1: StrictInt
    is_meas_idx_2: StrictInt


class StandardAdditionRequest(BaseModel):
    # 复用 /v1/assign 的参考峰表（id 唯一、时间严格递增）
    reference_peaks: list[ReferencePeak] = Field(min_length=2, max_length=40)
    target_ref_id: StrictStr
    is_ref_id_1: StrictStr
    is_ref_id_2: StrictStr
    tolerance_ms: StrictInt = Field(ge=0)
    injections: list[Injection] = Field(min_length=3, max_length=12)


class ResidualOut(BaseModel):
    # 按进样顺序；area_ratio = 目标峰面积 / 第一枚内标面积
    added_concentration: int
    area_ratio: FractionOut
    predicted_area_ratio: FractionOut
    # residual = area_ratio - predicted_area_ratio（观测减拟合）
    residual: FractionOut


class StandardAdditionResponse(BaseModel):
    # 含截距最小二乘：area_ratio = slope * added_concentration + intercept
    slope: FractionOut
    intercept: FractionOut
    # 原样浓度 = intercept / slope
    sample_concentration: FractionOut
    residuals: list[ResidualOut]


# ---------------------------------------------------------------------------
# 原始采样峰面积积分（POST /v1/integrate）
# ---------------------------------------------------------------------------

class IntensitySample(BaseModel):
    time_ms: StrictInt
    intensity: StrictInt = Field(ge=0)


class IntegrateRequest(BaseModel):
    # 5～500 个原始采样点；time_ms 必须严格递增
    samples: list[IntensitySample] = Field(min_length=5, max_length=500)
    # 积分起止下标（0 开始，start < end，峰顶须严格位于二者之间）
    start_index: StrictInt
    end_index: StrictInt
    # 2～60 个严格递增峰顶下标；相邻峰顶至少隔一个内部采样点
    peak_indices: list[StrictInt] = Field(min_length=2, max_length=60)


class SegmentOut(BaseModel):
    # 段边界（谷点为相邻两段共用），含采样下标与对应时间
    start_index: int
    end_index: int
    start_time_ms: int
    end_time_ms: int
    peak_index: int
    peak_time_ms: int
    # 减基线、截非负后按实际时间间隔梯形积分得到的约分面积
    area: FractionOut


class IntegratePeakOut(BaseModel):
    # 结构与 standard-addition 的 MeasuredPeak 一致，可直接喂给定量接口
    time_ms: int
    area: int = Field(ge=0)


class IntegrateResponse(BaseModel):
    segments: list[SegmentOut]
    # 各段面积分母的最小公倍数；area × multiplier 即下方整数面积
    multiplier: int
    # 按峰顶时间升序的整数峰（零面积保留）
    peaks: list[IntegratePeakOut]
