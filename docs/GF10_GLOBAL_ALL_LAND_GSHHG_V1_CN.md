# GF10 全球陆地10公里格网：GSHHG full本地操作手册

日期：2026-11-02。仓库 WuJH123/GEE_flooding。新基底不是旧GF10城市掩膜；本次只生成地理格网，不下载任何需要GEE的大影像。

## 设计

使用NOAA GSHHG 2.3.7 full-resolution（包含小岛）矢量多边形的全部陆地，严格用 L1（大陆/海岛）- L2（湖泊）+ L3（湖中岛）- L4（岛内水塘）+ L6（南极接地陆地）；不用L5南极冰前缘。凡GSHHG源中确有陆地且与10km格网相交面积>0的单元均保留，**不要求格网中心在陆地上**。GSHHG仍可能漏测现实中极微小的礁岛，因此不能声称绝对覆盖地球上每个小岛。

地理投影：EPSG6933仅适用于86°S-86°N，旧GF10的x_y编号和相同格网边界保留；86°N–90°N改EPSG6931，采用N_x_y前缀；90°S–86°S改EPSG6932，采用S_x_y前缀。三者纬度分区互斥，全部10,000m边长、100km²名义面积。务必保留每行grid_crs和land_fraction，不允许用6933旧GEE导出脚本直接处理极区。旧 data/reference/grid10_urban_2020.parquet 与182格实验表都保留、绝不覆盖。

## 1 下载官方Shapefile（约142MB，可复用本地）

官方下载：https://ftp.soest.hawaii.edu/gshhg/gshhg-shp-2.3.7.zip
NOAA产品：https://www.ngdc.noaa.gov/mgg/shorelines/shorelines.html
GitHub release提供的SHA256：8dbbe7e071e77e9e75f2d639239099ebca8d5c16d6a07df8169729d49f15cf41

PowerShell：

    $ROOT="E:\GEE_flooding"
    $SRC="E:\GEE_flooding_code"
    if (-not (Test-Path "$SRC\.git")) { git clone https://github.com/WuJH123/GEE_flooding.git $SRC }
    else { git -C $SRC pull --ff-only origin main }
    Set-Location $SRC
    git log -1 --oneline
    $PY="$ROOT\.venv\Scripts\python.exe"
    if (-not (Test-Path $PY)) { py -3.11 -m venv "$ROOT\.venv" }
    & $PY -m pip install -e "$SRC[test]"
    & $PY -m pytest -q

    $LAND="$ROOT\data\external\GSHHG_v237"
    New-Item -ItemType Directory -Force $LAND | Out-Null
    $ZIP="$LAND\gshhg-shp-2.3.7.zip"
    if (-not (Test-Path $ZIP)) {
        Invoke-WebRequest -Uri "https://ftp.soest.hawaii.edu/gshhg/gshhg-shp-2.3.7.zip" -OutFile $ZIP
    }
    $EXPECTED="8dbbe7e071e77e9e75f2d639239099ebca8d5c16d6a07df8169729d49f15cf41"
    if ((Get-FileHash $ZIP -Algorithm SHA256).Hash.ToLower() -ne $EXPECTED) { throw "GSHHG SHA256 mismatch" }
    $UNPACK="$LAND\source"
    if (-not (Test-Path $UNPACK)) { Expand-Archive -LiteralPath $ZIP -DestinationPath $UNPACK }
    $SHAPES="$UNPACK\GSHHS_shp\f"
    foreach ($lv in @(1,2,3,4,6)) {
      if (-not (Test-Path "$SHAPES\GSHHS_f_L$lv.shp")) { throw "GSHHG full L$lv missing" }
    }

## 2 先实际测试海岛和极地（不替代正式全球产品）

    & $PY -m gee_flooding.grid_global_land --root $ROOT --source $SHAPES --resolution f --smoke-bounds 178 -10 180 10 --tag gf10_pacific_smoke_v1
    & $PY -m gee_flooding.grid_global_land --root $ROOT --source $SHAPES --resolution f --smoke-bounds -35 -90 -15 -86 --tag gf10_antarctic_smoke_v1

局部QC只允许标记PILOT_REGIONAL_ONLY。如果源GSHHG全分辨率出现跨180度/极地几何错误，必须修复，不能忽略错误单元声称全球完整。

## 3 正式生成全部全球陆地 GF10（无 GEE）

    $OLD="$ROOT\data\reference\grid10_urban_2020.parquet"
    if (-not (Test-Path $OLD)) { throw "Earlier frozen GF10 not found" }
    & $PY -m gee_flooding.grid_global_land --root $ROOT --source $SHAPES --resolution f --legacy $OLD --tag gf10_global_land_gshhg_f_v1

输出位于 E:\GEE_flooding\data\reference\gf10_global_land_gshhg_f_v1 ：
- gf10_global_all_land.parquet 全部有正陆地面积的格网；
- gf10_zone_G.parquet 原6933同位置全球陆地；
- gf10_zone_N.parquet 北极等面积6931；
- gf10_zone_S.parquet 南极等面积6932；
- gf10_global_land_qc.json 分区格网数、总陆地面积、面积守恒、源Shapefile SHA256、旧ID对照；
- legacy_urban_cells_not_in_new_land.csv 旧城市GF10未被GSHHG陆地包围的差异清单。

    $NEW="$ROOT\data\reference\gf10_global_land_gshhg_f_v1"
    Get-Content "$NEW\gf10_global_land_qc.json"
    & $PY -c "import pandas as pd; d=pd.read_parquet(r'$NEW\gf10_global_all_land.parquet'); print('rows=',len(d),'area_km2=',d.land_area_km2.sum()); print(d.groupby(['zone','grid_crs']).agg(cells=('grid_id','size'),land_km2=('land_area_km2','sum')))"
    Import-Csv "$NEW\legacy_urban_cells_not_in_new_land.csv" | Select-Object -First 20

## 4 必须验收

1. 原6933旧ID和10km网格几何不改，极地ID带N_/S_以免碰撞。
2. 0<land_fraction<=1，每个小岛即使小于一格、格心在海上仍保留（前提是GSHHG full收录）。
3. 每个分区矢量带符号面积与所有网格内陆地面积合计相差不超过0.3%；必须包含南极接地陆地。
4. 原城市网格没有被静默删除；如有差异，给出真实海岸线/内湖/极区原因并审核。
5. 全球全陆地网格并非所有格网都要运行GEE。本次只冻结物理空间索引，后续区分国家、城市、气候和流域掩膜，复用本地已下载数据进行逐指标补齐。沿海格网同时保留100km²整格面积和真实land_area_km2，禁止把整格人口密度与陆地人口密度混淆。
6. 旧fig2_gee、fig2_local_exact和labels目前假设6933且存在旧城市掩膜；不能直接把新全陆地polar格网喂入旧脚本宣称全部指标完成。下一阶段需要基于grid_crs制作极地导出/全球分块适配器。

## 依据

NOAA GSHHG https://www.ngdc.noaa.gov/mgg/shorelines/shorelines.html
GSHHG分层 https://www.soest.hawaii.edu/wessel/gshhg/
NSIDC EASE网格 https://nsidc.org/data/user-resources/help-center/guide-ease-grids
EPSG 6933适用范围 https://epsg.io/6933
