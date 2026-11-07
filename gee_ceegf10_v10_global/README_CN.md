# GF10 全球 GEE 生产续跑（V10，2026-11-07）

## 2026-11-07 最新真实状态

- 气象事件暴露已经按冻结的 **275,152 个 GF10×UTC 代理日期**完成：378/378 项 V10 云任务均通过 Drive CSV 的日期、格网、IMERG 观测计数、数值和哈希 QC。最终文件为 `weather_exposure_GLOBAL_QC_PASS.parquet`，SHA-256 `9fcfa411cb74f3ee7c5273c2a57dc486a2ecafb1b0ac497cd0436ab49442581d`；ERA5 第一层土壤水分缺失 7,471 行，保持缺失。此处“全球”是审计后的全球事件日期样本范围，不是每个 GF10 的每日时间序列。最终报告见 `weather_assembly_report.json`。
- MERIT 两个直接原生像元→10 km 栅格的真实 60×60 试验（武汉 3,598 格、沿海 3,499 格）通过仿射、16 波段、GF10 成员和独立源像元 QC，实际费用分别 0.08539、0.05657 EECU 小时。西缘同样的 60×60 试验真实失败：`Reprojection output too large (7464x14100 pixels)`；失败记录保留，直接法在 `abs(grid_x//60)>=26` 的边缘桶禁用。三项原生面积加权表格试验（内陆 1,000 格、高纬 300 格、西缘 100 格）通过真实导出及独立源像元核查。
- `plan_merit_hybrid_v10.py` 完成冻结 1,395,471 格的互斥分配：已验收直接试验 7,097 格、624 个后续直接块 1,262,862 格、512 个原生加权任务 125,062 格、14 个接缝块 450 格仍隔离。计划精确守恒，校验见 `merit_hybrid_partition_qc.json`。西缘失败试验的 917 格已重新纳入原生方法，不计为通过。
- `merit_hybrid_runner.py` 的首批 6 项具名任务已经显式提交 GEE，账本为 `merit_hybrid_v10.sqlite`；其状态仍需按真实 operation 与 Drive QC 判定，未通过前不计完成。月度项目用量指标最近一次为 330.68 EECU 小时；提交预留上限 900 小时。首批六项三倍试验费率的预算预留 2.72 小时，不是实际费用。

继续命令（均默认只读，只有 `submit --execute` 新增 GEE 任务）：

```powershell
$P = 'E:\GEE_flooding\CEE_GF10_COST_OPT_V10_20261106'
$PY = 'E:\GEE_flooding\.venv\Scripts\python.exe'
& $PY "$P\merit_hybrid_runner.py" status --refresh
& $PY "$P\merit_hybrid_runner.py" audit --batch-limit 6
& $PY "$P\merit_hybrid_runner.py" submit --batch-limit 20
& $PY -m unittest -v "$P\test_v10_qc.py"
```

`audit` 自动下载已成功的任务、逐块校验并写 Parquet；如有失败立即停止该批 QC。首批六项没有真实科研 QC 前，不继续扩大提交。Cloud 任务已经提交后，本地电脑关机不影响运行。

本目录不覆盖 v3/v4/v7/v8 成果。冻结 GF10 为 1,395,471 个非南极正陆地面积格网，文件 SHA-256 为 `4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d`。使用独立 GEE 项目 `future-shuttle-513705-g9`。新增 GEE 结果写入 Google Drive，重计算在 GEE 云端执行，本地电脑关机不会取消已提交任务。

## 历史试验过程（以下旧进度以顶部最新状态为准）

- 378 项 V10 气象任务已一次性提交 GEE；**提交不等于完成或验收**。逐任务状态以 `weather_v10.sqlite` 和 GEE operation 复核为准。云盘 CSV 不要求永久逐个下载；`weather_runner.py audit-drive --execute` 每批在内存中读取和核验最多 10 项，落一份带来源哈希的 Parquet。未运行该本地 QC 时，云端仍可继续计算。
- `assemble_weather.py` 只拼接旧版已验收及 V10 已通过 QC 的结果，并对原始 GF10×UTC 集合去重。未全量覆盖时文件名明确含 `PARTIAL`。不得将其当全球完成品。
- 初版 MERIT 原生投影试验采用嵌套 `reduceRegions`，在西缘参考格复现 GEE 几何运算错误；两项旧任务已取消。等值连接修复了几何错误，但独立源像元显示，未经面积加权的高纬 UPA 均值偏差 1.64%；因此三项尚未运行的未加权试验也已取消，原始意图、任务 ID 和取消原因均保留。最终试验图对原生像元显式使用 `pixelArea` 加权的分子与分母，以 `grid_id` 连接直接源像元分位数。内陆、西缘、高纬三个原始 GF10 的 13 项独立源像元指标通过互动对照，均值最大相对差低于 0.002%，HAND 分位数的最大绝对差为源数据一个 0.1 m 量化级。此方法的武汉 1,000 格、格陵兰 300 格、西缘 100 格真实任务 `CLFVOQGWD2OAEPGMCRJO32HC`、`FZJWJHUXE7PZ2BYDKVRCL7EM`、`MO4NLS5O4BJZUVQNCXAEV6YU` 已提交，仍需云端执行、Drive CSV、16 项指标、原始 GF10 成员、独立源像元和 EECU 验收。`merit_native_tasks_v10.csv` 的 1,653 项是**候选计划，尚未全球提交**。
- 原 v3 两阶段 500 m→10 km MERIT 表达式在低纬 6×6 武汉及沿海真实试验与 v7 数值一致；高纬出现 `Too many input pixels per output pixel`，较大 8×8 还出现 `Reprojection output too large`。源原生投影方案属于新的统计估计方法；必须单独验收，不能与旧估计值无标识混合。
- `v10_science_method_decision.json` 和 `native30_weighted_v7_comparison.json` 记录了 30 格、16 指标对照。旧 v7 的部分分位数与独立原始像元明显不符，例如 `1090_360` 的 UPA p90 为 1.875 km²，而原始源像元及新原生方法均为 0.283 km²。新方法仍需真实批量导出和费用验收，现有旧值应保留来源版本，不与新值静默拼接。
- 更高效的直接栅格方案把 MERIT 源像元一次聚合到冻结 EPSG:6933 10 km 格，分位数设置 `maxRaw=150000`。四个内陆、沿海和西缘真实源像元互动探针的 16 波段均成功，其中均值和分位数与独立原始像元吻合；高纬格真实触发 65,536 输入像元上限，不能使用此方法。`merit_hybrid_candidate_plan.json` 将单格源像元包围框不超过 50,000 的 1,379,686 个安全 GF10 分配至 744 个至多 60×60 的候选栅格任务；另 15,335 格采用原生面积加权表格统计，高纬至少需要 52 项；接缝 450 格仍隔离。**该混合计划只读，未全球提交。**武汉和沿海两项真实 60×60 试验 `46UKCQYNFEU4LLQCMYTJWLRT`、`TBGLQTTVZHAEWEC4FYCKCUSE` 已提交，待导出、源像元对照及 EECU 验收。若通过，优先采用此较少任务且科学正确的方案。
- 原生像元风险盘点表明高纬 GF10 单格源像元包围框最多约 103,125 个像元；20 波段面积加权求和的 `maxPixelsPerRegion=2,500,000` 是按此上界设置的输入保护，不改变原始分辨率，也不绕过投影错误。分位数 `maxRaw=150,000` 覆盖该单格上界，避免默认直方图近似。具体语义见 [GEE 区域统计](https://developers.google.com/earth-engine/apidocs/ee-image-reduceregions)、[分位数](https://developers.google.com/earth-engine/apidocs/ee-reducer-percentile)及[像元面积](https://developers.google.com/earth-engine/apidocs/ee-image-pixelarea)。
- 14 个经度接缝隔离父块、450 个 GF10 保持隔离。`seam_weighted_interactive_qc.json` 对一个原始 GF10 的周期拆分几何做了 GEE 与独立源像元对照，HAND 均值仍差 0.91 m，p50/p90 各差约 0.4 m；**接缝恢复未通过科学闸门**，不得将 450 格纳入正式静态 Parquet 或填零。

## 科学合同

MERIT 固定 16 项：HAND 均值、海拔均值、上游汇流面积均值、永久水体比例、有效覆盖率、HAND≤2/5/10 m 比例、坡度均值、坡度≤2°比例、上游汇流面积最大值、最大值 `log1p`、HAND p10/p50/p90、汇流面积 p90。单位按源目录：高程和 HAND 为 m，汇流面积为 km²；坡度为度。缺失源覆盖不补零。

气象每个真实 GF10×UTC 日期提取：IMERG V07 permanent 当日累计 mm、半小时峰值 mm/h、当日 43 个完整滑动窗口的最大 3 小时累计 mm、前 7/14/30 天累计 mm、半小时观测计数（48/336/672/1440）；ERA5-Land 前一日土壤水分 1/2 层 m³/m³、气温 °C、降水 mm、径流 mm、U/V 风及风速 m/s。IMERG 雨强乘 0.5 小时变为半小时雨深；ERA5-Land 原始日累计 m 乘 1000 为 mm。新闻无报道日期只是未标记暴露，不是物理确认的无洪水日。

## 继续检查（PowerShell）

```powershell
$P = 'E:\GEE_flooding\CEE_GF10_COST_OPT_V10_20261106'
$PY = 'E:\GEE_flooding\.venv\Scripts\python.exe'
& $PY "$P\weather_runner.py" status
& $PY "$P\weather_runner.py" audit-drive --execute --max-qc-batches 10
& $PY "$P\assemble_weather.py"
& $PY "$P\native_merit_pilot_audit.py" --site wuhan_weighted
& $PY "$P\native_merit_pilot_audit.py" --site greenland_weighted
& $PY "$P\native_merit_pilot_audit.py" --site westedge_weighted
& $PY "$P\merit_direct_raster_audit.py" --site wuhan
& $PY "$P\merit_direct_raster_audit.py" --site coast
& $PY "$P\budget_v10.py"
& $PY -m unittest -v "$P\test_v10_qc.py"
```

`audit-drive --execute` 只执行本地质量验收，**不提交新 GEE 任务**。原 `submit-all` 已完成，禁止重复执行。两个原生 MERIT 试验通过且费用可接受后，才检查 1,653 项候选计划的分块成本并启动有界全球任务；目前不得启动。

## 主要来源与限制

- [MERIT Hydro v1.0.1 官方 Earth Engine 目录](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)
- [IMERG V07 官方 Earth Engine 目录](https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07)
- [ERA5-Land Daily Aggregated 官方 Earth Engine 目录](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
- [Earth Engine reduceRegions](https://developers.google.com/earth-engine/apidocs/ee-image-reduceregions)
- [Earth Engine 配额和批处理限制](https://developers.google.com/earth-engine/guides/usage)

本项目每月 1,000 EECU 小时；本轮为新提交设置 900 小时保守暂停阈值。Cloud Monitoring 可能滞后，应同时核对实际 operation 的 `batchEecuUsageSeconds`。当前静态 MERIT 全球完成率仍未达到论文所需的完整覆盖；所有可用数据以科学 QC 和 SHA-256 报告为准。

本仓库目录保存生产**源码快照**；真实 GF10、输入 Parquet、GEE 任务账本、Drive GeoTIFF/CSV 和 QC 报告在本机 `E:\GEE_flooding\CEE_GF10_COST_OPT_V10_20261106`，不得把空仓库源码视为已生产数据。`local_science_qc.py` 是在上述真实输入存在时运行的本地回归测试，未命名为 pytest 自动收集文件。源数据和任务凭证不得提交 GitHub。

预算口径见 `budget_v10.py` 和 `v10_budget_interpretation.json`。Google 的 `in_progress_usage_time` 在请求运行期间报告，`usage_time` 在成功结束时报告，月累计存在同一请求的重叠；两列直接相加只能作为极保守上界，**不是实际已用 EECU**。后续采用已完成请求、在途 operation 与非重复计数指标交叉核对，并对尚未运行任务做单独费用预测。
