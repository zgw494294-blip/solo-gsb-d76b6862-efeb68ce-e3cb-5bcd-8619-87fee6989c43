"""峰面积积分 HTTP 接口测试（TestClient 走真实 ASGI 栈）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def samples(times_intensities):
    return [
        {"time_ms": t, "intensity": i} for t, i in times_intensities
    ]


def payload(**over):
    body = {
        "samples": samples(
            [
                (0, 0), (1, 0), (2, 10), (3, 6), (4, 5),
                (5, 4), (6, 5), (8, 20), (9, 5), (10, 10),
            ]
        ),
        "start_index": 0,
        "end_index": 9,
        "peak_indices": [2, 7],
    }
    body.update(over)
    return body


def test_integrate_happy_path():
    r = client.post("/v1/integrate", json=payload())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["multiplier"] == 5
    assert data["peaks"] == [
        {"time_ms": 2, "area": 69},
        {"time_ms": 8, "area": 93},
    ]
    seg0, seg1 = data["segments"]
    assert set(seg0) == {
        "start_index", "end_index",
        "start_time_ms", "end_time_ms",
        "peak_index", "peak_time_ms", "area",
    }
    assert seg0["start_index"] == 0
    assert seg0["end_index"] == 5
    assert seg0["area"] == {"n": 69, "d": 5}
    assert seg1["start_index"] == 5
    assert seg1["end_index"] == 9
    assert seg1["area"] == {"n": 93, "d": 5}


def test_three_peaks_scaling_and_zero_retention():
    body = {
        "samples": samples(
            [
                (0, 0), (1, 0), (2, 0), (3, 10), (4, 2),
                (5, 4), (6, 5), (7, 20), (8, 5), (9, 2),
                (10, 4), (11, 8), (12, 16), (13, 6), (14, 1),
                (15, 0),
            ]
        ),
        "start_index": 0,
        "end_index": 15,
        "peak_indices": [3, 7, 12],
    }
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["multiplier"] == 2
    assert data["peaks"] == [
        {"time_ms": 3, "area": 17},
        {"time_ms": 7, "area": 52},
        {"time_ms": 12, "area": 60},
    ]


def test_422_on_sample_count_violations():
    body = payload()
    body["samples"] = samples((i, 0) for i in range(4))
    body["peak_indices"] = [1, 2]
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 422

    body = payload()
    body["samples"] = samples((i, 0) for i in range(501))
    body["end_index"] = 500
    body["peak_indices"] = [100, 200]
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 422


def test_422_on_peak_count_violations():
    body = payload()
    body["peak_indices"] = [2]
    assert client.post("/v1/integrate", json=body).status_code == 422


def test_422_on_non_strict_times():
    body = payload()
    body["samples"][3]["time_ms"] = 2  # 与前一点相等
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 422
    assert "strictly increasing" in r.json()["detail"]


def test_422_on_negative_intensity():
    body = payload()
    body["samples"][3]["intensity"] = -1
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 422


def test_422_on_adjacent_apexes_without_interior():
    body = payload(peak_indices=[2, 3])
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 422
    assert "interior sample" in r.json()["detail"]


def test_422_on_apex_not_between_bounds():
    body = payload(start_index=2)
    r = client.post("/v1/integrate", json=body)
    assert r.status_code == 422
    assert "strictly between" in r.json()["detail"]


def test_422_on_out_of_range_bounds():
    assert client.post(
        "/v1/integrate", json=payload(end_index=99)
    ).status_code == 422
    assert client.post(
        "/v1/integrate", json=payload(start_index=-1)
    ).status_code == 422


def test_422_on_wrong_types_and_missing_fields():
    # 布尔/浮点不能冒充整数
    body = payload(start_index=True)
    assert client.post("/v1/integrate", json=body).status_code == 422
    body = payload()
    body["samples"][0]["intensity"] = 1.5
    assert client.post("/v1/integrate", json=body).status_code == 422
    # 缺字段
    body = payload()
    del body["peak_indices"]
    assert client.post("/v1/integrate", json=body).status_code == 422


def test_peaks_feed_standard_addition_endpoint():
    # 端到端衔接：/v1/integrate 的 peaks 直接作为 /v1/standard-addition
    # 的 measured_peaks（面积字段同名同类型）。
    integrated = client.post(
        "/v1/integrate",
        json={
            "samples": samples(
                [
                    (0, 0), (1, 0), (2, 0), (3, 10), (4, 2),
                    (5, 4), (6, 5), (7, 20), (8, 5), (9, 2),
                    (10, 4), (11, 8), (12, 16), (13, 6), (14, 1),
                    (15, 0),
                ]
            ),
            "start_index": 0,
            "end_index": 15,
            "peak_indices": [3, 7, 12],
        },
    ).json()
    assert integrated["peaks"] == [
        {"time_ms": 3, "area": 17},
        {"time_ms": 7, "area": 52},
        {"time_ms": 12, "area": 60},
    ]

    refs = [
        {"id": "S0", "time_ms": 10},
        {"id": "T", "time_ms": 22},
        {"id": "S2", "time_ms": 37},
    ]

    def injection(concentration, target_area):
        return {
            "added_concentration": concentration,
            "measured_peaks": [
                integrated["peaks"][0],
                {"time_ms": 7, "area": target_area},
                integrated["peaks"][2],
            ],
            "is_meas_idx_1": 2,
            "is_meas_idx_2": 0,
        }

    sa = client.post(
        "/v1/standard-addition",
        json={
            "reference_peaks": refs,
            "target_ref_id": "T",
            "is_ref_id_1": "S2",
            "is_ref_id_2": "S0",
            "tolerance_ms": 0,
            "injections": [
                injection(0, 52),
                injection(10, 65),
                injection(20, 78),
            ],
        },
    )
    assert sa.status_code == 200, sa.text
    data = sa.json()
    assert data["sample_concentration"] == {"n": 40, "d": 1}
    assert all(row["residual"] == {"n": 0, "d": 1} for row in data["residuals"])


def test_existing_endpoints_still_work():
    # 回归：健康检查与 /v1/assign、/v1/standard-addition 不受影响
    assert client.get("/health").status_code == 200
    r = client.post(
        "/v1/assign",
        json={
            "reference_peaks": [
                {"id": "p0", "time_ms": 10},
                {"id": "p1", "time_ms": 22},
                {"id": "p2", "time_ms": 31},
                {"id": "p3", "time_ms": 34},
                {"id": "p4", "time_ms": 40},
                {"id": "p5", "time_ms": 55},
            ],
            "measured_times_ms": [3, 6, 14, 20, 22, 26, 36],
            "is_ref_id_1": "p0",
            "is_meas_idx_1": 1,
            "is_ref_id_2": "p4",
            "is_meas_idx_2": 5,
            "tolerance_ms": 0,
        },
    )
    assert r.status_code == 200
    assert r.json()["assignments"] == [1, 2, 3, 4, 5, 6]
