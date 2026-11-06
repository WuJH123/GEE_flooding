# CEE Figure 2：官方规则约束下的 GEE v9 自适应合批（2026-11-06）

**GitHub 源码目录**：`gee_ceegf10_v8_global_production/cee_v8/`。这是在已合并 v8 官方来源图、v6/v7 实测 QC 基础上的增量工程。它不改变16个 MERIT 源公式，也不把气象重分析当成真实淹没证据。

## 1. 不能超过的官方边界与经实测决定的边界

- 批处理任务最长生命周期 **10天**；项目待处理队列最多 **3000**，默认平均并行批任务**约2**（以项目实时配额为准）。任务队列数量、计算用量和运行时间是三个不同概念。不能通过把若干4×4矩形合并成全球大矩形来减少任务：90m源重投影图将超限。
- 用户当前自述 Contributor 1000 EECU小时/月。保留100小时科研额度余量，**推荐本项目停止提交阈值900 EECU小时**。本程序通过 Cloud Monitoring 月总项目 Completed+In-progress EECU（包括其他用户）进行保守判断；如果权限不足则阻断提交。监控指标属于 BETA，可能存在报告延时，因此不是官方的硬费用保证。若实际层级不是1000，应据实调整。
- MERIT 16波段保留先前 80 km halo 的 v6 收敛证据。v8源`ceeprodgee/ee_model.py`原封不动，聚合仍为原始90m→500m→10km均值/最大值，以及90m→10km原始像元分位数（禁止先求500m分位数）。
- IMERG V07只使用`status=permanent`历史源。半小时深度=原波段`precipitation`（mm/h）×0.5h；日48、前7日336、前14日672、前30日1440。日内43个三小时滚动窗口。ERA5-Land `DAILY_AGGR`土壤含水量和气温是**前一个完整UTC日**；`total_precipitation_sum`与`surface_runoff_sum`已累计，单位m转mm。异常负雨量标记，不强行补0。
- 真实时间窗口、新闻日期及UCDB城市归属仍受 Figure 1 来源精度限制。无报道不能当作真实无洪水对照；GEE的气象一致性不是物理洪水验证。

## 2. 理论分组数量，不等于 GEE 已验证预算

v4冻结的安全父块共有 **16,860**（安全陆地1,395,021格），v6/v7已验收部分复用，接缝 14父块/450格需独立处理：

| 候选MERIT打包尺寸 | 单个导出矩形最多GF10像元 | 完全连续、无遮挡时16,860父块理论最少任务数 | 90m输入计算包围面积上限（含80km halo，估算） |
|---|---:|---:|---:|
| 1×1旧父块 | 100 | 16,860 | 约7.8百万原生像元 |
| 2×2 | 400 | 4,215 | 约15.1百万 |
| 3×3 | 900 | 1,874 | 约24.5百万 |
| 4×4 | 1,600 | 1,054 | 约36.5百万 |

实际规划包含海岸线不规则范围、已有验收块、投影接缝排除、低陆地密度拒绝打包，**必须以本地 `preview` 输出为准**。表中任务数仅是极限理想值，不能视为最终正式计划，也不能线性外推EECU。

气象任务按 `grid_id×UTC代理日` 守恒。v8原有196,496个唯一基础格日（43,694个报道格日 +152,889未标记候选格日并去重），加报道源D±1做不确定性分析。预设每任务**不超过400个格网日、2个UTC日期**，日期内聚合一次源时间图，最终任务数由真实密度决定。若服务器报错自动将气象子任务二分；不会声称减少原生30分钟影像抽取工作量。

## 3. 一次完整部署（Windows PowerShell）

请使用 GitHub `main` 的完整v9更新代码，部署到 `E:\GEE_flooding\CEE_GF10_GLOBAL_EE_V8_20261106`，**不要覆盖已有的 `plans`、`reports` 和 `downloads`**；若旧目录已有生产 SQLite 任务账本，必须继续原任务，不允许直接更换打包计划。

```powershell
$ROOT='E:\GEE_flooding'
$PKG="$ROOT\CEE_GF10_GLOBAL_EE_V8_20261106"
$PY="$ROOT\.venv\Scripts\python.exe"
$env:PYTHONPATH="$PKG;$ROOT\CEE_GF10_EFFICIENT_V3_20261105"
Set-Location $PKG
& $PY -m pip install -r "$PKG\requirements.txt"
& $PY -m pytest "$PKG\tests" -q -W error

# 如果从未生成过v8计划：一次性冻结科学数据和天气事件计划
& $PY -m cee_v8 --root $ROOT --pkg $PKG prepare --max-rows 400 --max-days 2

# 不消耗GEE：查看实际可能减少多少 MERIT 任务
& $PY -m cee_v8.optimizer_cli_v9 --root $ROOT --pkg $PKG preview

# 生成 3 类地理条件 x 3 种合并尺寸 = 最多9个正式 GEE 先导任务
& $PY -m cee_v8.optimizer_cli_v9 --root $ROOT --pkg $PKG plan-pilots

# 已配置Cloud Monitoring Viewer、EE API、Drive API/ADC后，在本地重复执行，
# 每次核验/推进少量任务；不需要重新创建新项目。
& $PY -m cee_v8.optimizer_cli_v9 --root $ROOT --pkg $PKG tick-pilots --storage drive --max-inflight 2
& $PY -m cee_v8.optimizer_cli_v9 --root $ROOT --pkg $PKG status
```

等9个先导任务进入真实终态后执行：

```powershell
# 只可能批准有三类环境、多波段数值对照、掩膜一致性和运行时间证据的尺寸。
& $PY -m cee_v8.optimizer_cli_v9 --root $ROOT --pkg $PKG approve
# 在尚未register的 v8 计划上写入新的MERIT任务清单，并保留原始CSV和哈希
& $PY -m cee_v8.optimizer_cli_v9 --root $ROOT --pkg $PKG promote
& $PY -m cee_v8 --root $ROOT --pkg $PKG register

# 自动重新从Cloud Monitoring读取当月全项目用量，预算熔断900h，平均2并发
& $PY -m cee_v8 --root $ROOT --pkg $PKG run `
   --storage drive --max-inflight 2 --max-unaccepted 10 `
   --month-used-eecu 0 --budget-limit-eecu 900 `
   --execute --confirm CEE_GF10_GLOBAL_EE_V8_20261106
```

`--month-used-eecu 0`在v9里是**已弃用兼容占位参数**，不可作为真实月用量：真实值必须每轮从Cloud Monitoring读取成功，缺权限立即停止任务提交。运行前可改成真实数字以便日志对账，但调度不信任静态数字。

全部`ACCEPTED`后：

```powershell
& $PY -m cee_v8 --root $ROOT --pkg $PKG assemble-weather
# 必须先另行通过14个MERIT接缝父块、450格独立科学验收
& $PY -m cee_v8 --root $ROOT --pkg $PKG seam-diagnostic
& $PY -m cee_v8 --root $ROOT --pkg $PKG assemble-merit
```

**实际生产恢复和费用警告**：若任何先导任务没有达到科学等价验收，禁止自动提升块尺寸。可以用原v8 1×1保守计划继续，或者通过真实验收的较小打包尺寸；不允许绕过 QC 手改JSON为PASS。月额度不是硬截断，Cloud Monitoring也存在延迟，建议另在 Cloud Console 设置每日EECU配额、保留余量。

## 4. 开源及官方文档

- [Earth Engine批任务生命周期和队列](https://developers.google.com/earth-engine/guides/processing_environments)
- [EE 代码最佳实践：过滤和reproject](https://developers.google.com/earth-engine/guides/best_practices)
- [EE导出精确affine和maxPixels](https://developers.google.com/earth-engine/guides/exporting_images)
- [非商业Contributor 1000h/月](https://developers.google.com/earth-engine/guides/noncommercial_tiers)
- [Cloud Monitoring指标](https://developers.google.com/earth-engine/guides/monitoring_usage)
- [Cloud Monitoring指标类型](https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h)
- [MERIT Hydro](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)
- [IMERG V07](https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07)
- [ERA5-Land DAILY_AGGR](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
