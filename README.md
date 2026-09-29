# 离线色谱峰归属 / 峰面积积分 / 标准加入法定量 API

- **峰面积积分**：对 5～500 个原始 `{time_ms, intensity}` 采样点，以相邻峰顶之间的最低内部点
  （谷点）为共用分界分段，逐段做**连线基线校正 + 按实际时间间隔的精确梯形积分**。
- **峰归属**：基于 **两对互异内标** 对实测色谱峰进行正斜率仿射时间校准，并将实测峰与参考峰做
  **保序、一对一** 的最优归属。
- **标准加入法定量**：对 3～12 次加标进样逐次复用上述归属定位目标峰，以第一枚内标面积归一化后，
  对 (加标浓度, 面积比) 做含截距精确最小二乘，给出斜率、截距与原样浓度。

典型链路：**原始采样 → `/v1/integrate` 得到整数 `{time_ms, area}` 峰表 →
`/v1/standard-addition` 定量；峰时间供 `/v1/assign` 归属**。

Python 3.12 + FastAPI，全部时间/偏差/面积/拟合计算使用 `fractions.Fraction` 精确有理数，
返回约分后的 `n/d`。

## 一条命令启动

```bash
docker compose up --build -d
```

- 本地端口：**http://localhost:8000**
- 峰面积积分：`POST http://localhost:8000/v1/integrate`
- 峰归属：`POST http://localhost:8000/v1/assign`
- 标准加入法定量：`POST http://localhost:8000/v1/standard-addition`
- 健康检查：`GET http://localhost:8000/health`
- 交互文档：`http://localhost:8000/docs`（Swagger UI）

停止：`docker compose down`

## `POST /v1/integrate`（原始采样峰面积积分）

### 请求

`Content-Type: application/json`

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `samples` | 数组，长度 **5～500** | 每项 `{time_ms: 整数, intensity: 非负整数}`；`time_ms` **严格递增** |
| `start_index` / `end_index` | 整数 | 积分区间下标（从 0 开始），要求 `0 ≤ start_index < end_index < len(samples)` |
| `peak_indices` | 整数数组，长度 **2～60** | 峰顶下标，**严格递增**；每个峰顶严格位于起止下标之间，相邻峰顶之间**至少有一个内部采样点** |

```bash
curl -s http://localhost:8000/v1/integrate \
  -H 'Content-Type: application/json' \
  -d '{
    "samples": [
      {"time_ms": 0,  "intensity": 0},
      {"time_ms": 1,  "intensity": 0},
      {"time_ms": 2,  "intensity": 10},
      {"time_ms": 3,  "intensity": 6},
      {"time_ms": 4,  "intensity": 5},
      {"time_ms": 5,  "intensity": 4},
      {"time_ms": 6,  "intensity": 5},
      {"time_ms": 8,  "intensity": 20},
      {"time_ms": 9,  "intensity": 5},
      {"time_ms": 10, "intensity": 10}
    ],
    "start_index": 0,
    "end_index": 9,
    "peak_indices": [2, 7]
  }'
```

### 积分规则

1. **谷点分界**：对每对相邻峰顶 `p_k、p_{k+1}`，在内部点
   `p_k+1 … p_{k+1}-1` 中取 `intensity` 最低者为两段共用分界；
   强度并列时取**最早下标**。段边界依次为
   `start_index → 谷点₁ → … → 谷点ₘ₋₁ → end_index`，各段首尾相接、互不重叠。
2. **连线基线**：每段以两端采样点的连线为基线，段内每个采样点将
   `intensity − 基线值` **截为非负**（低于基线的点贡献 0，不会产生负面积）。
3. **精确梯形积分**：对相邻采样点按其**实际时间间隔**
   `time_ms[i+1] − time_ms[i]` 做梯形累加；时间轴不必等距。全程使用
   `fractions.Fraction`，不引入浮点。
4. **统一放大**：每段面积返回约分分数 `{n, d}`；取**所有面积分母的最小公倍数**
   为 `multiplier`，将各面积放大为整数峰面积。

### 响应

- `segments[]`：与 `peak_indices` **同序**，每项含段边界下标与时间
  （`start_index/end_index/start_time_ms/end_time_ms`，谷点为相邻两段共用）、
  峰顶下标与时间（`peak_index/peak_time_ms`）、约分面积 `area {n, d}`。
- `multiplier`：全部面积分母的最小公倍数；`整数面积 = 分数面积 × multiplier`。
- `peaks[]`：`{time_ms, area}` 整数数组，**按峰顶时间升序**（下标与时间均严格递增），
  **零面积峰保留**。字段结构与 `/v1/standard-addition` 的 `measured_peaks` 完全一致，
  可直接喂给定量接口；其 `time_ms` 可作为 `/v1/assign` 的 `measured_times_ms` 归属。

上例中峰顶 2（int 10）与峰顶 7（int 20）之间的内部点 idx3/4/5/6 强度为 6/5/4/5，
谷点为 **idx5（int 4）**；两段面积分别为 `69/5` 与 `93/5`：

```json
{
  "segments": [
    {"start_index": 0, "end_index": 5,
     "start_time_ms": 0, "end_time_ms": 5,
     "peak_index": 2, "peak_time_ms": 2,
     "area": {"n": 69, "d": 5}},
    {"start_index": 5, "end_index": 9,
     "start_time_ms": 5, "end_time_ms": 10,
     "peak_index": 7, "peak_time_ms": 8,
     "area": {"n": 93, "d": 5}}
  ],
  "multiplier": 5,
  "peaks": [
    {"time_ms": 2, "area": 69},
    {"time_ms": 8, "area": 93}
  ]
}
```

### 衔接示例：积分结果送入定量 / 归属接口

三峰采样（16 个点、峰顶下标 `[3, 7, 12]`）积分返回：

```json
{
  "multiplier": 2,
  "peaks": [
    {"time_ms": 3,  "area": 17},
    {"time_ms": 7,  "area": 52},
    {"time_ms": 12, "area": 60}
  ]
}
```

将各次进样的 `peaks` 原样作为 `/v1/standard-addition` 的 `measured_peaks`
（面积字段同名同类型，无需换算），并以两枚内标峰（时间 3 与 12）归一化：

```bash
curl -s http://localhost:8000/v1/standard-addition \
  -H 'Content-Type: application/json' \
  -d '{
    "reference_peaks": [
      {"id": "S0", "time_ms": 10},
      {"id": "T",  "time_ms": 22},
      {"id": "S2", "time_ms": 37}
    ],
    "target_ref_id": "T",
    "is_ref_id_1": "S2",
    "is_ref_id_2": "S0",
    "tolerance_ms": 0,
    "injections": [
      {"added_concentration": 0,
       "measured_peaks": [
         {"time_ms": 3,  "area": 17},
         {"time_ms": 7,  "area": 52},
         {"time_ms": 12, "area": 60}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 0},
      {"added_concentration": 10,
       "measured_peaks": [
         {"time_ms": 3,  "area": 17},
         {"time_ms": 7,  "area": 65},
         {"time_ms": 12, "area": 60}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 0},
      {"added_concentration": 20,
       "measured_peaks": [
         {"time_ms": 3,  "area": 17},
         {"time_ms": 7,  "area": 78},
         {"time_ms": 12, "area": 60}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 0}
    ]
  }'
```

本例面积比恰好为 `area_ratio = (13/600) × concentration + 13/15`（残差全为 0），
原样浓度 `(13/15) / (13/600) = 40`。若需先做保留时间归属，取
`measured_times_ms = [p.time_ms for p in peaks]`（即 `[3, 7, 12]`）调用 `/v1/assign`
即可——参考时间 10/22/37 对应内标校准 `t_cal = 3·t_meas + 1`。

### 错误处理（HTTP 422）

以下情况均返回 `422 Unprocessable Entity`，响应体为 `{"detail": "原因"}`：

- 采样点数不在 5～500，或峰顶数不在 2～60；
- 采样时间不是严格递增，或强度为负；
- `start_index/end_index` 越界、`start_index ≥ end_index`；
- 峰顶下标越界或不是严格递增；
- 峰顶未严格位于起止下标之间，或相邻峰顶之间没有内部采样点（下标差 < 2）；
- 类型错误（布尔不会被当作整数、浮点不会被截断为整数）或缺少必填字段。

## `POST /v1/assign`（峰归属）

### 请求

`Content-Type: application/json`

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `reference_peaks` | 数组，长度 2～40 | 每项 `{id, time_ms}`；`id` 唯一，`time_ms` 整数且按时间**严格递增** |
| `measured_times_ms` | 整数数组，长度 2～60 | 实测峰时间（下标从 **0** 开始） |
| `is_ref_id_1` / `is_ref_id_2` | 字符串 | 两个互异的内标参考峰 id，必须存在于参考峰中 |
| `is_meas_idx_1` / `is_meas_idx_2` | 整数 | 两个互异内标的实测下标，范围 `[0, len(measured_times_ms)-1]` |
| `tolerance_ms` | 非负整数 | 校准后允许的最大绝对偏差 |

> 两对内标的书写顺序可以互换，服务端会自动归一化；但两对必须同向：
> 沿参考时间递增方向，实测下标也必须递增（不可交叉），且两个实测内标时间严格有序，
> 从而保证仿射斜率严格为正。

```bash
curl -s http://localhost:8000/v1/assign \
  -H 'Content-Type: application/json' \
  -d '{
    "reference_peaks": [
      {"id": "p0", "time_ms": 10},
      {"id": "p1", "time_ms": 22},
      {"id": "p2", "time_ms": 31},
      {"id": "p3", "time_ms": 34},
      {"id": "p4", "time_ms": 40},
      {"id": "p5", "time_ms": 55}
    ],
    "measured_times_ms": [3, 6, 14, 20, 22, 26, 36],
    "is_ref_id_1": "p0", "is_meas_idx_1": 1,
    "is_ref_id_2": "p4", "is_meas_idx_2": 5,
    "tolerance_ms": 0
  }'
```

### 响应

- `assignments`：与参考峰**同序**一一对应，值为配对的实测下标，未配对为 `null`。
- `unpaired_meas_indices`：未配对的实测下标，升序。
- `matches`：每个配对峰一条记录，`calibrated_time_ms` 为实测时间经校准后的值，
  `signed_deviation_ms = 校准值 − 参考值`；两者均为约分分数 `{"n": 分子, "d": 分母}`，
  分母恒为正（负值体现在分子上）。

上例的校准直线为 `校准值 = (3/2) × 实测值 + 1`：

```json
{
  "assignments": [1, 2, 3, 4, 5, 6],
  "unpaired_meas_indices": [0],
  "matches": [
    {"ref_id": "p0", "ref_index": 0, "meas_index": 1,
     "calibrated_time_ms": {"n": 10, "d": 1},
     "signed_deviation_ms": {"n": 0, "d": 1}},
    {"ref_id": "p1", "ref_index": 1, "meas_index": 2,
     "calibrated_time_ms": {"n": 22, "d": 1},
     "signed_deviation_ms": {"n": 0, "d": 1}},
    {"ref_id": "p2", "ref_index": 2, "meas_index": 3,
     "calibrated_time_ms": {"n": 31, "d": 1},
     "signed_deviation_ms": {"n": 0, "d": 1}},
    {"ref_id": "p3", "ref_index": 3, "meas_index": 4,
     "calibrated_time_ms": {"n": 34, "d": 1},
     "signed_deviation_ms": {"n": 0, "d": 1}},
    {"ref_id": "p4", "ref_index": 4, "meas_index": 5,
     "calibrated_time_ms": {"n": 40, "d": 1},
     "signed_deviation_ms": {"n": 0, "d": 1}},
    {"ref_id": "p5", "ref_index": 5, "meas_index": 6,
     "calibrated_time_ms": {"n": 55, "d": 1},
     "signed_deviation_ms": {"n": 0, "d": 1}}
  ]
}
```

非整数示例（参考 `[10,25,40]`、实测 `[6,15,26]`、容差 2）中，实测 15 校准为
`47/2`，对参考 25 的有符号偏差为 `-3/2`：

```json
{"n": 47, "d": 2}
{"n": -3, "d": 2}
```

### 归属规则

1. **内标强制配对**：两对互异内标始终配对，并据此确定仿射变换
   `t_cal = slope·t_meas + intercept`，其中 `slope > 0`。
2. **容差门限**：其余峰仅当 `|t_cal − t_ref| ≤ tolerance_ms` 时允许配对。
3. **一对一 + 保序**：每个参考峰最多配一个实测峰（反之亦然），
   配对链上参考下标与实测下标都严格递增；允许任意一侧的峰连续跳过。
4. **优化目标**（依次比较）：
   1. 配对数最多；
   2. 所有配对的绝对偏差之和最小；
   3. 仍并列时，取 `(参考下标, 实测下标)` 配对序列（按参考下标排序）字典序最小。

实现上，两对内标把问题切为三个互不重叠的独立区间，每个区间用 LCS 风格动态规划求解
（规模 ≤ 40×60，远低于毫秒级），最后合并强制配对。分数全程不转浮点，无精度损失。

### 错误处理（HTTP 422）

以下情况均返回 `422 Unprocessable Entity`，响应体为 `{"detail": "原因"}`：

- 参考峰 `id` 重复，或参考时间不是严格递增；
- 参考峰/实测峰数量超出 2～40 / 2～60 的范围；
- 内标参考 id 不存在，或两个 id 相同；
- 内标实测下标越界、相同；
- 两对内标顺序不一致（实测下标交叉），或两个实测内标时间不严格有序
  （导致斜率不为正或无定义）；
- `tolerance_ms` 为负；
- 类型错误（布尔不会被当作整数、浮点不会被截断为整数）或缺少必填字段。

## `POST /v1/standard-addition`（标准加入法定量）

对 3～12 次加标进样逐次复用 `/v1/assign` 的保序归属定位目标峰，以**第一枚内标**的面积
归一化目标面积，再对 `(加标浓度, 面积比)` 做含截距最小二乘：

```
area_ratio = slope × added_concentration + intercept
原样浓度 sample_concentration = intercept / slope   （x 轴截距绝对值）
```

全程使用 `fractions.Fraction` 精确求解闭式最小二乘，不引入浮点。
`injections[].measured_peaks` 可直接取自 `/v1/integrate` 响应的 `peaks`
（字段同名同类型，参见上文[衔接示例](#衔接示例积分结果送入定量--归属接口)）。

### 请求

`Content-Type: application/json`

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `reference_peaks` | 数组，长度 2～40 | 同 `/v1/assign`：`{id, time_ms}`，`id` 唯一、时间严格递增 |
| `target_ref_id` | 字符串 | 目标峰参考 id，必须存在且**不得**等于两枚内标 id |
| `is_ref_id_1` / `is_ref_id_2` | 字符串 | 两个互异内标参考峰 id（归一化使用**第一枚**的面积） |
| `tolerance_ms` | 非负整数 | 归属时允许的最大绝对偏差 |
| `injections` | 数组，长度 **3～12** | 每次进样一项，按进样（采集）顺序排列 |

`injections[]` 每项：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `added_concentration` | 非负整数 | 本次加标浓度；全部进样中**至少有两个不同值** |
| `measured_peaks` | 数组，长度 2～60 | 按采集顺序排列的实测峰 `{time_ms: 整数, area: 非负整数}` |
| `is_meas_idx_1` / `is_meas_idx_2` | 整数 | 两枚内标在本次 `measured_peaks` 中的下标（从 0 开始） |

```bash
curl -s http://localhost:8000/v1/standard-addition \
  -H 'Content-Type: application/json' \
  -d '{
    "reference_peaks": [
      {"id": "p0", "time_ms": 10},
      {"id": "p1", "time_ms": 20},
      {"id": "p2", "time_ms": 30},
      {"id": "p3", "time_ms": 40}
    ],
    "target_ref_id": "p1",
    "is_ref_id_1": "p2",
    "is_ref_id_2": "p3",
    "tolerance_ms": 0,
    "injections": [
      {"added_concentration": 0,
       "measured_peaks": [
         {"time_ms": 10, "area": 0},
         {"time_ms": 20, "area": 500},
         {"time_ms": 30, "area": 1000},
         {"time_ms": 40, "area": 800}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 3},
      {"added_concentration": 10,
       "measured_peaks": [
         {"time_ms": 10, "area": 0},
         {"time_ms": 20, "area": 560},
         {"time_ms": 30, "area": 1000},
         {"time_ms": 40, "area": 800}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 3},
      {"added_concentration": 20,
       "measured_peaks": [
         {"time_ms": 10, "area": 0},
         {"time_ms": 20, "area": 620},
         {"time_ms": 30, "area": 1000},
         {"time_ms": 40, "area": 800}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 3},
      {"added_concentration": 50,
       "measured_peaks": [
         {"time_ms": 10, "area": 0},
         {"time_ms": 20, "area": 800},
         {"time_ms": 30, "area": 1000},
         {"time_ms": 40, "area": 800}],
       "is_meas_idx_1": 2, "is_meas_idx_2": 3}
    ]
  }'
```

本例面积比恰为 `area_ratio = (3/500) × concentration + 1/2`（残差全为 0），
原样浓度 `(1/2) / (3/500) = 250/3`：

```json
{
  "slope": {"n": 3, "d": 500},
  "intercept": {"n": 1, "d": 2},
  "sample_concentration": {"n": 250, "d": 3},
  "residuals": [
    {"added_concentration": 0,
     "area_ratio": {"n": 1, "d": 2},
     "predicted_area_ratio": {"n": 1, "d": 2},
     "residual": {"n": 0, "d": 1}},
    {"added_concentration": 10,
     "area_ratio": {"n": 14, "d": 25},
     "predicted_area_ratio": {"n": 14, "d": 25},
     "residual": {"n": 0, "d": 1}}
  ]
}
```

（上示响应省略了浓度 20、50 的两条残差，结构相同。）

### 响应字段

- `slope` / `intercept`：约分分数 `{"n", "d"}`；要求 **slope > 0** 且 **intercept ≥ 0**。
- `sample_concentration`：原样浓度 `intercept / slope`（约分分数）。
- `residuals`：与 `injections` **同序**，每项含 `added_concentration`、
  观测 `area_ratio`（目标面积 ÷ 第一枚内标面积）、`predicted_area_ratio` 拟合值、
  `residual = 观测 − 拟合`；均为约分分数，分母恒正。

### 422 规则

除继承 `/v1/assign` 的全部校验外（参考峰、内标、容差等；任何一次进样归属失败都会在
消息中指出 **进样下标**，形如 `injection 2: ...`），本接口还可能因下列原因返回 422：

- 目标峰 id 不存在，或目标峰就是内标之一；
- 某次进样的目标峰在容差内**未归属**（消息指出进样下标）；
- 某次进样**第一枚内标面积为 0**（无法归一化；消息指出进样下标）；
- 加标浓度少于两个不同值；
- 最小二乘斜率不为正（≤ 0），或截距为负；
- 进样数不在 3～12、单次实测峰数不在 2～60、负浓度/负面积，以及严格类型错误或缺字段。

## 本地开发与测试

不用 Docker 时：

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 测试（另需 pytest、httpx）
pip install pytest httpx
pytest -q
```

测试包含固定边界用例，以及 400 组随机实例与全局暴力枚举（枚举所有保序配对链）对拍，
验证“最大配对数 → 最小绝对偏差和 → 字典序最小”三级目标；积分测试包含 200 组随机实例
与独立朴素实现对拍，验证谷点选取、基线截断、梯形面积与 LCM 放大。

## 目录结构

```
app/
  main.py               # FastAPI 应用、路由、422 异常映射
  models.py             # 严格类型的请求/响应模型
  integration.py        # 原始采样：谷点分段 + 基线校正 + 精确梯形积分（纯函数）
  assignment.py         # 仿射校准 + 区间 DP 归属（纯函数）
  standard_addition.py  # 标准加入法：逐次归属 + 精确最小二乘（纯函数）
tests/                  # API 测试与算法对拍测试
Dockerfile
docker-compose.yml
requirements.txt
```
