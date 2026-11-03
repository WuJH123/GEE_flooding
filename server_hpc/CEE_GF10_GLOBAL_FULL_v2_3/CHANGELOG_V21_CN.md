# GF10 CEE全本地处理 v2.1 – 修复与验证记录

版本日期：2026-11-03。根据服务器19:09:53的输出，旧v2程序在 `[stage] gisd` 之后只展示了 `Traceback` 首行，**实际最末行错误未随用户输入提供，因此无法证明具体的RAR/7-Zip错误原因。**

## 修复清单

1. **PowerShell 5.1日志错误**：旧版 `$ErrorActionPreference='Stop'` 与 `2>&1 | Tee-Object` 可能把Python第一行stderr变成终止异常，隐藏实际错误。新版 `scripts/run_with_log.py` 合并子进程 stdout/stderr，并保证完整文件日志，保留真实 exit code。
2. **GISD30 7-Zip前置检查**：在大规模分卷解压前，先确认已下载12个RAR及完整7z解压工具；可选调用 `7z t` 独立验证各RAR CRC。
3. **按数据源给出错误**：一旦GISD（或其他family）阶段失败，写入 `reports/cee_full_v2/stages/staged_gisd_failed.json`（其他family同名规则），不再仅有笼统的 Traceback。
4. **RAR安全解压及恢复**：临时目录位于 `data/working/cee_stage_scratch_v21`，先解压校验再按相对路径提升，仅对原暂存文件做SHA-256比较，发现冲突就拒绝覆盖；原始下载归档与已完成Parquet不会修改。
5. **ZIP重跑避免反复CRC**：首次解压完整校验CRC且写入QC。相同源和同样大小的文件有完成QC后，不再对整套WorldClim/大型FileGDB无意义地重复读取压缩前全部内容。原来源mtime/大小变化后仍会拒绝复用。
6. **Windows异常退出后的旧锁**：只有确认旧进程不再运行，才把旧 `global_run.lock` 重命名归档；不直接删除，不在活跃任务上抢锁。
7. **新增诊断及针对性执行**：`scripts/04_diagnose_gisd.ps1`、`scripts/05_stage_gisd_only.ps1`、`-StageOnly`；免手填GDB字段或5000格采样。
8. **全量数据任务保留**：其余原本的35本地下载文件、715分区、GMTED、WorldClim、GRIP4矢量/密度、RiverATLAS、UCDB、BasinATLAS、ERA5-EX与Groundsource流程仍在完整包中；无需GitHub下载源代码。

## 制作环境测试

`PYTHONPATH=. python -m pytest -q tests`：**30 passed，4 skipped**。跳过项由制作环境缺少 `pyarrow` / `exactextract` 所致；用户服务器已有这些库，应在服务器上执行预检并期望34项全部通过。Python语法编译、SHA256清单、ZIP完整性及解压副本测试均需通过后正式交付。

## 科研限制

修复解决工程报错路径和断点续跑，不代表自动证明所有全球格网的海岸裁剪、GISD源缺瓦片、WorldClim源单位、GMTED高程Maximum元数据冲突和洪涝样本物理真实性。结构性处理完成后仍应维持 `publication_ready=false`，直到科学独立QC通过。
