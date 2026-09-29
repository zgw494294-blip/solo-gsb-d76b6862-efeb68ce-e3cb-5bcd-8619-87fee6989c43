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
