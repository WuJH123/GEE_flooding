# 直接交给 Codex：CEE 论文全球 GF10 GEE v9 官方规则受限自适应合批正式生产

你是负责CEE Figure 2（**不是 Nature Cities 主文**）全球水文遥感和Earth Engine正式科研数据工程的高级工程师。

**任务**：使用已合并GitHub主分支 `WuJH123/GEE_flooding` 的 `gee_ceegf10_v8_global_production` 和其 v9 打包优化模块，在 `E:\GEE_flooding` 完成全球非南极陆地1,395,471 GF10的MERIT Hydro 16项静态指标，与Figure 1审计196,496唯一 GF10×UTC代理日及D±1敏感性日的IMERG V07/ERA5-Land正式暴雨暴露数据。

严格要求：

1. 先阅读包内`README_V9_CN.md`及官方GEE配额、Processing Environments、MERIT/IMERG/ERA5目录。验证新v9代码及所有旧v8 regression/CI。冻结 GF10 SHA `4ebf864cf2f02ed02faaab42ccb179bb8d6e0a6293aee5e6a155f6ed2b21858d`，同一独立云项目`future-shuttle-513705-g9`。不覆盖旧v6/v7已验收、旧GEE操作或UUID来源表。
2. 按README运行 v8 prepare（weather≤400rows/2dates）与 v9 preview，输出实际 MERIT factor1/2/3/4计划数量，不把近似理论下限当实测。保留已验收863 MERIT格与46历史气象格日，不重计费。
3. `plan-pilots`自动选取可验证的海岸/内陆/高纬，分别2×2、3×3、4×4合并；`tick-pilots`执行真实9项GEE导出，用v7已验收MERIT16波段参考逐像元、逐波段检查值/掩膜，实际记录task ID、operation、EECU、运行时间、SHA。只批准通过3种环境的最大尺寸。任何科学偏差或超时，优先自动选择较小尺寸，不虚报全全球完成。
4. `approve`→`promote`→`register`。promote只能在旧v8任务账本尚未开始时发生，必须备份未打包任务清单与源哈希。禁止覆盖已有的sqlite、plan和source。之后启动有界的v8 run调度。新任务应真正减少云端数，同时保持10km GF10 EPSG6933、MERIT80km halo和原v3 16波段公式。失败的已验证打包可二分，不允许重复提交旧父任务或丢失陆地格。正式云端超过10天期限会被自动标失败，须设计可重启，不靠一个大请求跑全地球。
5. IMERG v07只用permanent；日48/7d336/14d672/30d1440；最大3h是日内43个连续窗口。ERA5-Land为D−1完整UTC日，转单位且保留原始异常/缺失。天气案例结果只是报道响应暴露而不是洪水真值；原报道日期应保留UTC代理标签。
6. Cloud Monitoring读取官方`earthengine.googleapis.com/project/cpu/usage_time`（completed）及`project/cpu/in_progress_usage_time`，按America/Los_Angeles每月1日重置；监测实际1000h Contributor项目总量，v9预警/暂停阈值900h，推荐并行2。配额不足/授权不足立即安全暂停，不能使用静态`$USED=0`欺骗审计。数据库保存真实GEE操作、文件哈希和QC。
7. 14 MERIT反子午线隔离父块/450 GF10仍须独立原生90m源像元科学验证，并完成后形成独立数据和审计；在完成前不允许标记1,395,471行MERIT全域通过。不要把该问题通过扩大全球重投影图或填0回避。
8. 只在完整GEE任务SUCCEEDED、文件下载、16波段/日期计数、缺测、格网与计划守恒通过后运行不带`--allow-partial`的`assemble-weather`与`assemble-merit`。记录每个结果对应的SHA256、来源和EECU，不允许虚构完成。
9. 故障请自动排查，必要时补充分层真实GEE测试、修复脚本、更新GitHub并合并。最终给出任务数降低比例、实际费用、成功/失败/隔离数量、全球格网覆盖、格日覆盖、科学差异和剩余论文所需独立物理洪涝验证。

在未取得原始E盘Parquet或GEE项目授权时，只报告实际完成的本地代码及GEE计划，不声称远程云任务已运行或研究已经满足正式投稿标准。
