# CEE GF10 GEE正式生产 v4 边界恢复包（2026-11-05）

## 定位与最重要结论

这是**完整可运行的恢复侧车代码包**，专门修复已安装 v3 的 GEE 生产异常，不覆盖已通过的 v3 MERIT、GEE资产或任务账本。MERIT 16 波段原生科学定义仍由已通过武汉 Gate C 的 v3 `ceeprodgee.ee_model.merit` 执行；因此必须**保留并加载 v3**，不要单独拿这个包脱离 v3 运行。项目固定为 `future-shuttle-513705-g9`。没有实时GEE权限的本包生成过程**没有提交任何云任务**，不声称边缘真实导出已通过。

### 当前真实证据

- GF10 EPSG:6933全球非南极 1,395,471 个有正陆地面积格；v3 `merit_all.csv` 有16,874个10×10父块，预估127.93 EECU-hours并非生产实测。
- 武汉 MERIT v3 10×10、16波段，成功下载，和 Gate C 基线相对误差p95约0.128%；上一次 10×11 被QC拒收。
- 首个全球父块 `merit_-1740_-240_10`只有3个真正的GF10陆地格，父块矩形跨越投影西界，GEE错误导出3474×10，QC正确拒收。这不是源数据计量值问题，更不能把3474列简单截掉当成有效结果。
- 方法测试 `event_method_20230601`: IMERG 4/4样本完整，ERA5-Land 2/4有值；无真实病例–对照GF10×UTC日冻结表，动态数据正式生产**尚不能执行**。旧 v3 task ledger EECU 约0.0267h，不代表整个Cloud项目月度用量。

## 修复方案（对应谷歌官方）

1. **用GF10已知陆地格的最小包围矩形**代替固化的10×10父块作为计算范围：这是按 `grid_x/grid_y` 整数坐标精确裁剪，不重新投影格网，也不缩减实际应覆盖陆地格数量。对于原失败块，实际应为约2列，而非10列——准确行数来自用户本机冻结Parquet，不凭日志猜测。原有父块ID仍作为任务键保留。
2. 只允许在EPSG:6933有效投影坐标范围内的矩形自动导出。超出有效域的真实接缝小岛/边界格单独列入`merit_quarantine_v4.csv`，**不得宣称全球覆盖100%**。
3. 云计算使用矩形完整区域以免裁掉源像元，导出 `region` 使用**像元中心包络±1m**以避免额外首尾行列。维持 `crsTransform=[10000,0,0,0,-10000,0]` 的全球固定网格；`maxPixels=200`强制GEE在再次把2×N误转成几千列时直接失败，不产生异常大文件。
4. 单任务完成之后本地QC逐项检查 **EPSG6933、完整仿射变换、紧凑矩形精确行列、16波段、HAND和UPA约束、任务来源/内容SHA-256**；任何不一致停止，不允许下一任务。
5. 新ledger在本包独立目录下；v3通过/失败/重试任务全部只读保留并做指纹快照。旧失败任务并不因此被标记成功，也不因旧账本的失败QC阻塞 v4 新的合法重试。
6. 事件数据单独冻结、审计：`reported_case`是真实报道正例；`matched_unreported_exposure`是没有报道的同类暴露，不代表真实没有洪涝。必须提供匹配对、城市、风暴ID、UTC日期及观测来源，才能生成事件GEE计划；不存在这些数据就必须暂停。

参考Google官方技术依据：
- https://developers.google.com/earth-engine/guides/exporting_images
- https://developers.google.com/earth-engine/guides/best_practices
- https://developers.google.com/earth-engine/guides/projections

## 安装要求

- 原有`E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105`或`E:\GEE_flooding\gee_ceegf10_v3_efficient`已经部署、其 `config\production.json` 和 `reports\task_ledger.json` 仍在，`pilot_merit_passed=true`，并且冻结 GF10 的路径/SHA一致。
- 原虚拟环境拥有Python 3.12、earthengine-api、pandas、pyarrow、numpy、pyproj、rasterio、pytest。直接复用，不重新注册GEE项目。
- **首次操作前备份整个v3 config/reports/downloads；不要用新脚本覆盖旧TIF或删除之前3474列的失败审计。**

## 按顺序运行（Windows PowerShell）

将ZIP复制到 `E:\GEE_flooding`：

```powershell
$ROOT='E:\GEE_flooding'
Expand-Archive -LiteralPath "$ROOT\CEE_GF10_GEE_RECOVERY_V4_20261105.zip" -DestinationPath $ROOT
$P="$ROOT\CEE_GF10_GEE_RECOVERY_V4_20261105"
Set-Location $P
Set-ExecutionPolicy -Scope Process Bypass -Force

# 1. 离线测试、只读核查旧v3身份，冻结V4独立配置及历史快照；不使用GEE费用
.\scripts\00_init.ps1 -Root $ROOT

# 2. 解析原16,874个父块与GF10真实陆地分布，自动拆分安全任务/接缝隔离任务（不提交）
.\scripts\01_plan_safe.ps1 -Root $ROOT

# 3. 原失败首块只读预览。核对实际紧凑输出行列、地理范围与投影变换
.\scripts\02_submit_one_edge.ps1 -Root $ROOT -Key 'merit_-1740_-240_10'

# 4. 执行恰好一个首块重试。仍然不是全球批量提交
.\scripts\02_submit_one_edge.ps1 -Root $ROOT -Key 'merit_-1740_-240_10' -Execute

# 5. 复查GEE状态/本次费用；只有云端成功后下载对应TIFF
.\scripts\03_status_and_audit.ps1 -Root $ROOT
```

### 下载 GeoTIFF 与QA

在本轮专属Google Drive目录 `CEE_GF10_GEE_EDGE_RECOVERY_V4_20261105`，下载文件 `CEE_GF10_GEE_EDGE_RECOVERY_V4_20261105_merit_-1740_-240_10.tif` 到：

`E:\GEE_flooding\CEE_GF10_GEE_RECOVERY_V4_20261105\downloads\`

随后：

```powershell
.\scripts\03_status_and_audit.ps1 -Root $ROOT -Key 'merit_-1740_-240_10' -Audit
```

看到 `ACCEPTED` **并不是全球生产全部完成**，只说明第一个安全紧凑块通过。真正接缝QUARANTINE任务仍须另建几何策略验证，不能直接排除地理研究总体。

### 后续单个安全块（全量计划保存在 plans 下）

```powershell
$PY='E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105\.venv\Scripts\python.exe'
if(-not (Test-Path $PY)) {$PY='E:\GEE_flooding\.venv\Scripts\python.exe'}
$V3='E:\GEE_flooding\CEE_GF10_EFFICIENT_V3_20261105'
if(-not(Test-Path $V3)){$V3='E:\GEE_flooding\gee_ceegf10_v3_efficient'}
$env:PYTHONPATH="$P;$V3"
& $PY -m cee_recover.run preview --key auto
# 需确认具体键；避免使用无意的自动批处理
& $PY -m cee_recover.run submit --key 'merit_1090_360_10'
# 显式 --execute --confirm 后才会启动；每块成功+下载+audit，再允许下一块
```

上述例子中的第二个任务键仅为命令格式举例；实际使用 `plans/merit_safe_v4.csv` 中的已注册`tile_key`，不要按示例提交不存在的任务。使用 PowerShell `02_submit_one_edge.ps1 -Key <真实tile_key> -Execute` 无需手填确认token。

### 保存并合并已通过的V4恢复块

```powershell
& $PY -m cee_recover.run merge
```

仅得到 `merit_v4_recovery_partial.parquet`，包括全量1,395,471个GF10行、已通过块的16指标以及其他缺测NaN。需要后续与v3其他已通过块严格按GF10 ID与来源指纹合并；本代码**不会**把PARTIAL错误命名为GLOBAL_COMPLETE。

## 事件组（当前应先执行到样本审计）

```powershell
# 尚未有真实审计冻结样本时：运行这个命令仅会提示缺口，不提交任务
.\scripts\04_event_cohort.ps1 -Root $ROOT

# 取得真实已独立匹配、且未泄漏训练集结果的事件表后，再运行：
# .\scripts\04_event_cohort.ps1 -Root $ROOT -Cohort 'E:\GEE_flooding\data\case_control_gf10_dates_audited.parquet'
```

事件表必填 `grid_id`, `date_utc`, `case_control`, `pair_id`, `storm_id`, `city_id`, `label_source`, `sampling_protocol`。不从新闻单独生成“无洪水”负例。成功冻结后才通过 `plans\event_gee_tasks_v4.csv` 逐批选择已注册`tile_key`，再运行：

```powershell
# 先dry-run，再明确提交一个真实日期×区域任务；非示例虚构日期
# .\scripts\05_event_submit.ps1 -Root $ROOT -Key '<计划中已有的tile_key>'
# .\scripts\05_event_submit.ps1 -Root $ROOT -Key '<计划中已有的tile_key>' -Execute
# .\scripts\06_event_audit.ps1 -Root $ROOT -Key '<相同tile_key>'
```

最终事件模型的 M0、M1、M2 输入必须保留`source_valid_fraction`和原始日期、数据来源的审计字段。ERA5-Land缺失不能用0插值。风险预测仍叫洪涝报道响应，直到Figure 3外部物理验证通过。

## 专业限制与不容误用

- 该包的科学计算部分保留v3已通过的 MERIT 16波段表达式；v4在**导出矩形和任务安全性**上修复。新裁切导出逻辑未在GEE服务端真实提交测试，因此正式第一块仍是工程复验，需要任务完成后读取TIF并实际验收。
- 极西端及极东端 `QUARANTINE_SEAM` 仍需后续单独建立经度分割/坐标系处理，不能声明全球MERIT全部取得。
- 原报账本中 `SUCCEEDED`但`local_qc_pass=false` 的异常3474列TIF仍保留审计，绝不计入数据有效率。
- v4默认不允许自动并发数千个任务。任务数量与总EECU须以每批真实运行计量更新，不能把127.93小时作为保证。
