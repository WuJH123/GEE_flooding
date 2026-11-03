# CEE GF10 Global Full v2.3 — 单次修复与全球继续执行

适用 `E:\WJH_CEE`：GF10 1,395,471格、715分区，WorldClim/GMTED/GHSL完成，109项静态栅格中108项可直接缓存复用；仅GRIP4总道路密度`.asc`缺CRS导致阻断。服务器不需要连接GitHub。

## 首先复制ZIP到远程服务器

把 `CEE_GF10_GLOBAL_FULL_v2_3.zip` 复制到 `E:\WJH_CEE\`，打开 Windows PowerShell：

```powershell
$ROOT = 'E:\WJH_CEE'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GLOBAL_FULL_v2_3.zip" -DestinationPath $ROOT
$PKG = "$ROOT\CEE_GF10_GLOBAL_FULL_v2_3"
Set-Location $PKG
Set-ExecutionPolicy -Scope Process Bypass -Force

# A. 验证源代码与完整服务器测试，不重复安装任何依赖
.\scripts\00_prepare_full.ps1 -Root $ROOT -SkipPip

# B. 只修复官网GRIP4道路密度ASC的WGS84 PRJ，自动核对真实网格尺寸与边界
.\scripts\08_prepare_grip_crs.ps1 -Root $ROOT

# C. 复用108/109已完成静态来源，继续全部715分区和剩余本地数据
.\scripts\07_resume_after_provider_fix.ps1 -Root $ROOT `
  -RasterJobs 4 -RasterWorkers 16 -VectorJobs 2 -VectorWorkers 16

# D. 全部任务真正完成后再运行结构性验收
.\scripts\02_verify_all_full.ps1 -Root $ROOT
```

**若只想执行一次启动命令**，可运行 `scripts\09_resume_v23.ps1 -Root $ROOT`，其内部依次完成上述A/B/C（不自动运行最后的结构验收）。

## 预期结果与边界

修复后输出 `E:\WJH_CEE\reports\cee_full_v2\grip4_ascii_crs_audit_v23.json`，其中 `status=GRIP4_WGS84_5ARCMIN_NATIVE_COORDINATES_VERIFIED`，`metadata_after.crs` 可能是 `OGC:CRS84` 或 `EPSG:4326`；它们在已核验的WGS84经纬度坐标应用中等价。

重新运行时 `[raster full] inputs=109, cached_complete=108, new=1` 是理想预期；之前数据若被单独改变，实际数量以任务指纹为准。接下来新的GRIP4原生统计也应完成715格网分区；然后流水线会继续ERA5-EX、GISD30、行政区/UCDB/BasinATLAS、全全球GRIP4道路及RiverATLAS河网矢量、Groundsource和最终宽表。**GRIP4道路矢量25,758,453条和RiverATLAS河流8,477,883条属于后续大任务，不能把“来源识别成功”当作“全部计算成功”。**

不得使用`--max-cells 5000`。保留 `E:\WJH_CEE\data\derived`，千万不要删除先前全域结果，不要同时运行v2.1/v2.2/v2.3。

## 若严格验证不通过

查看 `reports\cee_full_v2\grip4_ascii_crs_audit_v23.json` 和新的 `reports\cee_full_v2\full_run_v21_*.log`（v2.3继续复用原日志命名逻辑）、`reports\cee_full_v2\failed_stage.json`。

只在官方源确实4320×2160、全球界限和5角分网格核验通过后才补`.prj`。如果尺寸或界限异常，命令会终止；**不得跳过地理配准校验强行赋予EPSG:4326**。数据产品仍需GSHHG海岸陆地裁剪、GRIP道路矢量独立对照及其他科学QC，不能自动视为论文可发表。
