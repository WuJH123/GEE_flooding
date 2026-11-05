# CEE GF10 GEE 投影边缘生产修复 v4（2026-11-05）

**这是完整、独立可用的边界恢复/正式MERIT生产增量包**，以已部署并预检通过的 `gee_ceegf10_v3_efficient` 为数据/模型基础。GEE完整既有科学模型继续以GitHub主仓库v3源码为准；v4不复制旧项目或覆盖历史账本。不能脱离本地v3运行。

## 诊断与安全决定

- 武汉 MERIT 10×10/16波段、100有效格、Gate C相对误差p95=0.128%，**数值方法保持**。
- 首个全球块 `merit_-1740_-240_10` 旧导出3474×10必须封存、保留EECU账本，不能裁剪/重采样后作为成果。
- EPSG:6933在赤道上的有效横坐标约 ±17,367,530.445m，完整块左边是−17,400,000m。EE将完整投影越界矩形传递到经纬范围可导致区域展开。正常块以像元**中心范围**+冻结10km仿射变换精确导出；投影边缘块使用实测陆地GF10网格中心点的`reduceRegions(first)`，导出含完整GridID和16指标的CSV表，不给非法投影整块出GeoTIFF。
- **必须先在武汉用point-table新算一遍并与已通过的16波段Gate C独立GeoTIFF对照**。只有p95相对误差 ≤1%才放行边缘正式块。0.128%是当前v3 raster对照，**并非v4 point方法已通过**。
- v3原始`reports/task_ledger.json`永远只读，v4以单独账本`reports/boundary_v4_ledger.json`记账。旧失败任务由`quarantine`生成包含任务ID、旧账本哈希、原费用、异常尺寸的恢复记录；没有删除或把它设为通过。
- 一次最多提交一个新任务：上一个GEE操作成功、真实EECU可读、本地CSV/GeoTIFF严格审核为通过，才能提交下一项。对非边缘块设置`maxPixels=1000`而非2e6，避免3474列异常导出浪费费用。
- 正式事件数据不在本包中自动合成；在任何ERA5/IMERG正式任务前，必须独立冻结 `grid_id/date_utc/match_set_id/case_control/source_family/sampling_rule/city_id`。未报道的日期叫unlabeled control，不是确认未发生洪水。

## 用户电脑 E:\GEE_flooding PowerShell 操作（默认不提交）

将ZIP放到 `E:\GEE_flooding`，解压：

```powershell
$ROOT='E:\GEE_flooding'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GEE_BOUNDARY_RECOVERY_V4_20261105.zip" -DestinationPath $ROOT
$P="$ROOT\CEE_GF10_GEE_BOUNDARY_RECOVERY_V4_20261105"
Set-Location $P
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\01_preflight_and_plan.ps1
```

无须修改v3，当前`E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105`已部署；v4自动探测v3和其虚拟环境，读取原本确认过的Cloud项目和GF10 SHA256。此步纯本地，不耗费EECU。

### Step 2：先隔离旧版失败块（不会删除数据）

由于旧v3中`merit_-1740_-240_10`仍为`SUCCEEDED`但本地QC拒绝，v4安全闸门会在任何新GEE提交前检查它。**因此必须先执行：**

```powershell
.\scripts\03_quarantine_v3_edge.ps1
```

这只是把已知3474×10失败记录记入v4隔离报告，源账本和原始GeoTIFF均原样保留。之后才能执行武汉验证。

### Step 3：武汉 point-table 独立验证

```powershell
.\scripts\02_wuhan_table_pilot.ps1             # DRY_RUN
.\scripts\02_wuhan_table_pilot.ps1 -Execute    # 仅提交1项新表格计算任务
.\scripts\06_status.ps1
```

任务成功后在原v3 `production.json` 中指定的Drive目录下载 `CEE_V4_merit_1097_367_10_TABLE_PILOT_POINTS.csv` 至：

`E:\GEE_flooding\CEE_GF10_GEE_BOUNDARY_RECOVERY_V4_20261105\downloads`

下载后：

```powershell
$V4="$ROOT\CEE_GF10_GEE_BOUNDARY_RECOVERY_V4_20261105"
$V3="$ROOT\CEE_GF10_EFFICIENT_V3_20261105"
$PY="$V3\.venv\Scripts\python.exe"
$env:PYTHONPATH="$V4;$V3"
& $PY -m cee_boundary_v4 audit --key merit_1097_367_10_TABLE_PILOT
```

如果本机缺少 `E:\GEE_flooding\gee_ceegf10_v1\reports\gate_c_drive_tifs\gate_c_merit_v2_wuhan_10x10.tif`，必须将以前已验收的真正参考文件复制过来。程序不会以自己的结果作独立参照。

### Step 4：重新导出边缘块为表格

```powershell
.\scripts\04_edge_submit.ps1                 # DRY_RUN，首个正式块应显示POINT_TABLE
.\scripts\04_edge_submit.ps1 -Execute        # 仅提交1项西侧边缘块表格
.\scripts\06_status.ps1
```

任务成功后下载 `CEE_V4_merit_-1740_-240_10_POINTS.csv` 到v4 `downloads`：

```powershell
& $PY -m cee_boundary_v4 audit --key merit_-1740_-240_10
```

该块只导出在固定GF10中真实存在的陆地cell，而不是一个3474×10的无效大区域。QA必须逐个ID对齐；不准把空列重采样为0。

### 下一块、后续完整全球产出

```powershell
.\scripts\05_next_task.ps1                 # DRY_RUN
.\scripts\05_next_task.ps1 -Execute        # 仅一项正常10×10，或自动变为POINT_TABLE
.\scripts\06_status.ps1
```

按账本显示的`key`和`file`在Drive下载对应原始导出，并运行：

```powershell
& $PY -m cee_boundary_v4 audit --key '<显示的任务key>'
```

成功后才重复`05_next_task.ps1 -Execute`。每一项都必须独立通过QC并登记真实EECU。不建议直接提交16,874项任务；先拿到一个边缘表格和两个不同地理位置的正常raster对照，再测实际EECU和失败率，之后考虑已审批的地区分批生产。

将当前已完成并验收的源安全拼接为全世界1395471行的**部分宽表**：

```powershell
.\scripts\07_merge_partial.ps1
```

输出 `data\GF10_merit_v4_verified_partial.parquet` 和 `.qc.json`，报告已覆盖/缺失的真实GF10数量；未完成时不会伪称全球完整。

### IMERG/ERA5-Land正式事件准备

```powershell
.\scripts\08_audit_cohort.ps1
```

此步骤只核查预期在 `E:\GEE_flooding\data\frozen\case_control_gf10_dates.parquet` 的真实样本。若还没有该文件，安全停止。由已核对的Figure1事件来源和独立匹配对照构建后，才将`grid_id,date_utc`送入v3的`event-plan`并执行真实事件提取。任务的选择/配对与气象暴露变量计算相互独立；不能使用当天降雨量选负样本。

## 下一步的科研限制

- 16,874份独立10x10小文件不是全球大批量的效率最优终态；本次优先恢复安全、准确和可验证性，再使用已验收块的费用基准设计区域聚合任务。
- 若某个GF10陆地格中心自身超出EPSG6933有效范围，`validate_frozen_subset`会拒绝导出，并将其列为源几何/坐标适用范围的专项缺口；不能悄悄删除或移动格子。
- 本包的5项回归是离线测试，**还未通过新的Wuhan point-table GEE在线实测**；本次没有提交任何GEE任务。通过后才能推进正式全球生产。
- 官方依据：https://developers.google.com/earth-engine/guides/exporting_images 、https://developers.google.com/earth-engine/guides/best_practices 、https://developers.google.com/earth-engine/guides/projections 。
