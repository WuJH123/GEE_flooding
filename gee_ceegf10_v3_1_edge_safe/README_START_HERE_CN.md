# CEE GF10 GEE v3.1：EPSG:6933边界导出修复与断点恢复

**当前唯一高优先级阻断问题：** 已通过小范围武汉MERIT v3的10×10、16波段，但首个全球 MERIT 块 `merit_-1740_-240_10` 被 Earth Engine 以3474×10导出、QC拒绝。该10×10块跨EPSG6933有效经度边界，只有3个真正冻结GF10正陆地格网。本包避免重新导出宽达近全球的GeoTIFF：仅对该块的合法GF10中心点用冻结的0原点10km投影采样，导出16字段+grid_id的**CSV**。其它合法投影内部块继续按武汉已通过的10×10 GeoTIFF算法计算。**不重复此前MERIT武汉试验或IMERG/ERA5方法试验**。

## 1. 代码与数据复用约束

* 旧目录：`E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105`，保留原 `config/production.json`、`reports/task_ledger.json` 及下载文件。
* 新目录：`E:\GEE_flooding\CEE_GF10_GEE_EDGE_SAFE_V31_20261105`，独立部署。
* 旧独立Cloud项目 `future-shuttle-513705-g9` 保持不变，绝不跨项目读取旧资产；默认无GEE任务。
* 原GF10基底1,395,471个正陆地格，EPSG6933/10000米、原网格id不变；16波段MERIT字典不变。
* 2026-11-05报告：v3已报告消耗约0.02670338 EECU-hours，只是已登记任务，不是项目月度全部使用量。
* 图像总计16,874个10×10规划块，不可未经成本复核一次性全量提交。
* **缺少真实GF10×UTC病例–对照表：禁止正式IMERG/ERA5-Land事件提取。**

## 2. 当前电脑 PowerShell 一键执行顺序

将本ZIP放在 `E:\GEE_flooding\CEE_GF10_GEE_EDGE_SAFE_V31_20261105.zip`。

```powershell
$ROOT='E:\GEE_flooding'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GEE_EDGE_SAFE_V31_20261105.zip" -DestinationPath $ROOT
$P="$ROOT\CEE_GF10_GEE_EDGE_SAFE_V31_20261105"
Set-Location $P
Set-ExecutionPolicy -Scope Process Bypass -Force
& "$P\scripts\00_import_existing_v3.ps1" -Root $ROOT
& "$P\scripts\01_preview_west_edge.ps1" -Root $ROOT
```

`00_import_existing_v3.ps1` 将旧 v3 的完整任务账本和配置 **只复制一次**，验证新旧project、grid SHA、run_id，旧的通过QC结果（例如武汉下载影像）会验证哈希后复制到新 `downloads`。旧文件和旧项目从不覆盖。测试失败或GF10路径不正确即停止。

`01_preview_west_edge.ps1` 必须显示 `kind=edge_csv`、正确的 `grid_ids` 和实际格网数量（报告预期3格）。不能再出现 full projected bbox `[-17400000,...]` 作为图片 `region`。此阶段不调用GEE。

### 3. 仅提交这次已失败首块的修复任务

```powershell
& "$P\scripts\02_submit_west_edge_repair.ps1" -Root $ROOT
```

上述命令具有明确人工确认 `REJECT_3474X10_EXPORT`（用户已经提供原始QC）；如果保留旧的3474×10 GeoTIFF，可附加 `-BadTif` 实际文件路径，要求读取后确认宽高，否则拒绝重新提交。它会检查以往所有任务已终结、检查EECU记录与预算，再只启动**一个**CSV边界任务。旧任务标记 `quarantine` 和 `superseded_by`，`local_qc_pass` 永远为false；旧失败数据保留原样。

成功任务完成后到Google Drive下载其CSV，放入新包 `downloads`，文件名必须与运行日志及新账本一致。查询及下载审计：

```powershell
& "$P\scripts\03_status_and_audit_edge.ps1" -Root $ROOT
```

必须得到 `EDGE_CSV_QC_PASS_NEEDS_PHYSICAL_QA`，包括恰好所有冻结GF10 `grid_id`、16波段、物理数值单调关系和SHA256。**未下载CSV前，不重复提交任务。**

### 4. 下一块及所有后续块

```powershell
& "$P\scripts\04_resume_next_merit_one.ps1" -Root $ROOT
& "$P\scripts\06_audit_latest_completed.ps1" -Root $ROOT
```

`04` 每次只提交一个冻结MERIT计划中的新块；**普通内部区域为GeoTIFF，EPSG6933边缘区域则为grid_id CSV**。任务成功后需下载到 `downloads`，再运行 `06` 验收。所有块均自动按实际投影边界选模式，不要求填层名或文件路径。为了保护1000小时额度，当前代码没有无审计地循环提交16,874个任务的命令。

### 5. 结果合并（可用于检查阶段性成果）

```powershell
& "$P\scripts\05_merge_accepted_merit.ps1" -Root $ROOT
```

合并原生GeoTIFF与边界CSV为 `data/gf10_merit_partial_verified.parquet`，不以零代替缺失。**本阶段输出只是已验收块的部分产品，不是全球正式完成。**最终所有139.5万GF10 ID都应有合法来源区域、覆盖率和下载QC；仅凭行数1,395,471不等于全部水文值齐全。

## 3. 科学、GEE和网络风险

1. EPSG6933官方有效投影域x约±17,367,530.45米、y约±7,324,184.56米。边缘合法GF10中心点使用 `sampleRegions(projection=ee.Projection(WKT, [10000,0,0,0,-10000,0]))`，Export.table.toDrive CSV不再传出问题 `region`。
2. 如果某个正陆地GF10格子本身部分伸出EPSG6933有效投影域，CSV数值仍只表示**可解析投影内**的部分；任务记录 `partial_projection_domain=true`，必须另行地理空间核验，不能把它称为完整100km²统计。
3. 原MERIT重采样方法可能有区域间的原生聚合误差；世界不同气候/地形区还需独立抽样对照。武汉相对p95为0.128%，不是全球精度证明。
4. 本包34项离线测试和模拟EE导出接口测试，不等于边界CSV在真正GEE线上已成功；**仅提交一个边界任务**进行实证。
5. 地表覆盖WorldCover已改为服务器本地官方ESA COG路线，不会重新在GEE提交。
6. GEE内样本采集和EECU任务记录保留项目隔离与已用量审计；批量任务必须先完成单块下载和QC。
7. 失败任务账本不可删除，先前3474×10栅格不得裁切后当作合格结果。

## 4. 官方技术参考

- Earth Engine影像导出CRS与仿射：https://developers.google.com/earth-engine/guides/exporting_images
- `sampleRegions`与固定投影：https://developers.google.com/earth-engine/apidocs/ee-image-sampleregions
- CSV表格导出：https://developers.google.com/earth-engine/apidocs/export-table-todrive
- 2026 EPSG6933投影定义：https://epsg.io/6933
- Earth Engine任务费用：https://developers.google.com/earth-engine/guides/monitoring_usage
