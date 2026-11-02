# Figure 2 第一阶段：GF10 本地静态宽表（2026-11-02）

本手册仅处理冻结总纲中的 M04（10km地形、汇流、建成区和土地覆盖）。不下载新数据、不提交GEE、不运行动态气象训练，绝不宣称172/182样本已代表全球。此前真实样本是40个城市/182个GF10，2020 GHSL BUILT-S 已提取182/182格；模型尚缺MERIT、WorldCover、建成空间形态等变量。

## 一、为什么不把天、年和静态指标提前混成一张大表？

**主表键必须分开，使用同一个冻结EPSG:6933 10km GF10网格ID：**

A. S 静态/固定参考宽表（键：grid_id）。自然地形MERIT HAND、坡度、upa是准静态；GHSL 2000和2020是各自纪元快照，2000→2020变化是历史特征；WorldCover 2021是固定当期地表参考，不能当作2021–2025逐年实测。它们都可以用作冻结Fig2的固定背景，但必须记录每个变量的原始年份和计算方法。2021 WorldCover属于回顾性2021环境信息，不一定能用于2021年早期的运营前瞻预测。

B. Y 历史年度/5年城市状态（键：grid_id + source_epoch）。GHSL历史2000、2005、2010、2015、2020等保存在独立历史表。只有真实有该时期来源才允许推入以时变城市属性为目标的模型；GHSL未来2025/2030部分是推算值，不能假装已观测。不要对每一天插值虚构城市土地覆盖。

C. D 日尺度气象面板（键：grid_id + UTC_date）。IME​RG每日24h降水、前7个完整日降水、每日3h最大滚动雨量和ERA5前一UTC日土壤水分，2021–2025年分别建立。不把日气象写入静态表。

D. E 暴雨事件/新闻（键：grid_id + storm_id，或严格备选grid_id + UTC_date）。风暴仅使用独立气象资料识别，Groundsource高定位特异性的报道作为“新闻有记录/无新闻未标记”标签。未报道不等于无积水。Figure3另做独立物理观测。

全文主模型在最后才按 grid_id 合并S和D，再接E。对2024年前瞻测试始终使用冻结的2020/2021环境参考，不使用2024–2025期中或未来信息更新特征。相对差异是固定参考下的迁移能力，不等于真实动态下水系统韧性。

## 二、同步独立代码仓库（E:\GEE_flooding 没有.git）

PowerShell：

    $ROOT="E:\GEE_flooding"
    $SRC="E:\GEE_flooding_code"
    if (-not (Test-Path "$SRC\.git")) { git clone https://github.com/WuJH123/GEE_flooding.git $SRC }
    else { git -C $SRC pull --ff-only origin main }
    Set-Location $SRC
    git log -1 --oneline
    $PY="$ROOT\.venv\Scripts\python.exe"
    if (-not (Test-Path $PY)) { py -3.11 -m venv "$ROOT\.venv" }
    & $PY -m pip install -e "$SRC[local,test]"
    & $PY -m pytest -q

不要删除、迁移或覆盖E:\数据集、D:\博士资料\GIS材料、E:\Global_flooding。后三者只读，旧20km气象/标签不得冒充GF10成果。

## 三、第一项必须执行：检查已下载候选数据

    $INV="$ROOT\outputs\dataset_inventory_20261031.csv"
    $GRID="$ROOT\data\reference\fig2_subset_local_v1\fig2_GF10_selected_grid.parquet"
    $BASE="$ROOT\data\derived\fig2_integrated_ghsl182_v2\fig2_GF10_resilience_indicators.parquet"
    foreach ($file in @($INV,$GRID,$BASE)) {
        if (-not (Test-Path $file)) { throw "真实历史文件未找到：$file" }
    }
    & $PY -m gee_flooding.fig2_preflight --root $ROOT --city-audit-v3 "$ROOT\outputs\fig1_v3_full_r2\ucdb_city_development_holdout.csv"
    & $PY -m gee_flooding.fig2_local_first --index $INV --root $ROOT --max-per-family 150 --tag fig2_local_candidates_nov02_v1

检查 reports\fig2_local_candidates_nov02_v1\fig2_local_candidates.csv 和 fig2_family_gaps.csv。它们只是候选文件/分辨率/坐标核查，不证明真实10km覆盖或量纲正确。Codex须逐文件核对来源、年代、原始波段、单位、nodata、投影、实际几何覆盖和许可。

## 四、第二项必须执行：立刻复用182格GHSL构建静态基线宽表

即使没有合格的MERIT/WorldCover本地栅格，也应运行基线装配器；真实缺失保留NaN，不填0，不联网。

    & $PY -m gee_flooding.fig2_static_local --root $ROOT --grid $GRID --baseline $BASE --tag fig2_static_baseline182_nov02_v1
    $OUT="$ROOT\data\derived\fig2_static_baseline182_nov02_v1"
    Get-Content "$OUT\fig2_local_static_qc.json"
    Import-Csv "$OUT\fig2_indicator_missingness.csv" | Format-Table -AutoSize

生成文件：
1. fig2_GF10_local_static_wide.parquet：每个冻结GF10唯一一行，已有GHSL2020直接复用；
2. fig2_static_indicator_dictionary.csv：各指标属于地形准静态、2000或2020快照、2000–2020变化，还是2021地表参考，带单位和完整率；
3. fig2_GF10_required_missing_by_grid.parquet：每个格网还缺哪些M1–M4及重要暴露变量；
4. fig2_indicator_missingness.csv：统计每项缺多少格；
5. fig2_local_static_qc.json：输入原始文件及QC SHA256、年份合同、缺口数量，不会标成已发表。

## 五、第三项：本地已有合格原生栅格按来源分批精确提取

现有 gee_flooding.fig2_local_exact 已支持精确原生像元交集；对原始地理坐标栅格不能把度当米、也不能直接用用于米制等面积栅格的Shapely后端。优先现有JRC ESRI:54009原生建成面。MERIT Hydro原生经纬度时必须先进行有物理单位核验的面积保守/连续变量合适的投影汇总处理，或留给第三阶段GEE，不能将简单重投影的值自动宣称为原生守恒。WorldCover分类重投影必须保持类别而非双线性。GISD30编码0=透水、1–8=1985–2020前期/各期不透水，不能平均原始年代码。

Codex从候选CSV找到确实合格的本地TIFF后，人工生成实际源路径manifest，示例如下（路径必须替换；示例不能直接运行）：

    {
      "variables": [
        {"name":"hand_m","dataset":"MERIT_HYDRO","epoch":"static","kind":"mean",
         "unit":"m","band":1,"paths":["E:/VERIFIED_EQUAL_AREA/HAND.tif"]},
        {"name":"upstream_area_km2","dataset":"MERIT_HYDRO","epoch":"static","kind":"mean",
         "unit":"km2","band":1,"paths":["E:/VERIFIED_EQUAL_AREA/upa.tif"]},
        {"name":"built_fraction_2000","dataset":"GHSL_BUILT_S_R2023A","epoch":"2000",
         "kind":"cell_sum","native_units":"m2_per_native_pixel","unit":"fraction",
         "band":1,"paths":["E:/VERIFIED_GHSL_2000_MOLLWEIDE/Built100m.tif"]}
      ]
    }

如果提取已有经审计的坡度栅格，变量名必须为slope_deg，数据集VERIFIED_DEM_SLOPE_DEGREES、native_units=degrees、derivation_checked=true。已有GHSL原生100m局部形态派生栅格需要注明1500m建成邻域均值核/1000m局部标准差核，且derivation_checked=true；不能把局部标准差称为正式的斑块连通/破碎度。

    $MANIFEST="$ROOT\data\reference\fig2_local_MANUAL_verified.json"
    if (-not (Test-Path $MANIFEST)) { throw "先由Codex按真实源文件生成并核查manifest" }
    & $PY -m gee_flooding.fig2_local_exact --root $ROOT --grid $GRID --manifest $MANIFEST --backend exactextract --start-row 0 --count 182 --min-coverage 0.95 --tag fig2_local_native182_nov02_v1

如果没有exactextract，安装本地包扩展[local]。慢速Shapely仅支持实际核验的ESRI:54009或EPSG:6933等面积米制源；不能把EPSG:4326直塞进去。

**将多个已审计本地批次与已有GHSL2020合并：**

    $NATIVE="$ROOT\data\derived\fig2_local_native182_nov02_v1\fig2_local_GF10_indicators.parquet"
    & $PY -m gee_flooding.fig2_static_local --root $ROOT --grid $GRID --baseline $BASE --local $NATIVE --tag fig2_static_local182_nov02_v2
    $OUT="$ROOT\data\derived\fig2_static_local182_nov02_v2"
    Get-Content "$OUT\fig2_local_static_qc.json"
    Import-Csv "$OUT\fig2_indicator_missingness.csv" | Format-Table -AutoSize

每新增一个实际通过fig2_local_exact审计的其他来源，加一个 --local 对应的Parquet路径；严禁为了清零缺失而手工造数据。冲突会直接报错。没有额外合格本地源时使用第四节的baseline-only输出即可。

## 六、后续模块如何接受此宽表？

- fig2_indicators 新增 --local-static <实际静态宽表路径>，在第二/第三阶段有GEE真实结果时可做缺口式合并，必须额外检查来源冲突；
- fig2_daily 新增识别 fig2_local_static_qc.json，仍要求M0–M4静态指标完整后才建模；
- fig2_prepare 原有GEE天气模式亦可接受这份本地静态表；
- 既有 fig2_backfill_plan 可直接对以上宽表做下一阶段缺口任务 dry-run，不需要现在提交：

    & $PY -m gee_flooding.fig2_backfill_plan --root $ROOT --grid $GRID --indicators "$OUT\fig2_GF10_local_static_wide.parquet" --scope extended --max-cells 20 --tag fig2_remaining_static_gap_nov02_v1

**本轮验收**：冻结格网ID逐格一致，文件年代来源可追溯，所有本地原始源有QC，无小于95%像元覆盖却被视为有效的指标，零未解决的来源冲突；建成比例与km²单位换算正确，NRES不超过总建成面积，2000+增长核对2020；每个仍缺失的GF10和变量明确列出。182格仍只能称为试验范围，全球扩展需分块、唯一标签、相同标准重新处理。
