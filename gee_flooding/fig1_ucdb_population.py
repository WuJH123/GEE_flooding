"""Inspect locally present official GHS-UCDB fields, export chosen 2020 city population.

No speculative field mapping. Caller must identify an actual UCDB column from
read_info before any population-size group is named.
"""
from pathlib import Path
import json,re
import pandas as pd
from .paths import safe_output,atomic_json

def inspect(root,gpkg,layer="GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A",
            population_field=None,tag="fig1_publication_v1"):
    import pyogrio
    p=Path(gpkg)
    if not p.is_file():raise FileNotFoundError(p)
    layers=[str(x[0]) for x in pyogrio.list_layers(p)]
    if layer not in layers:raise ValueError("UCDB layer missing; available "+repr(layers))
    info=pyogrio.read_info(p,layer=layer)
    fields=[str(x) for x in info["fields"]]
    options=[x for x in fields if re.search(r"(?i)pop|inhabit|resident|2020",x)]
    idfield=next((x for x in ["ID_UC_G0","ID_UC","city_id"] if x in fields),None)
    if idfield is None:raise ValueError("Official city ID field missing")
    out=safe_output(root,f"outputs/{tag}/ucdb_population")
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=False)
    details={"official_gpkg":str(gpkg),"layer":layer,
             "id_column":idfield,"field_count":len(fields),
             "population_field_candidates":options,
             "selected_population_field":population_field,
             "note":"Select a verified total population count at reference year 2020, not an interpolated density or share."}
    if population_field:
        if population_field not in fields:raise ValueError("Selected column not present in UCDB")
        from pyogrio import read_dataframe
        df=read_dataframe(gpkg,layer=layer,columns=[idfield,population_field],
                          read_geometry=False)
        if df[idfield].isna().any() or df[idfield].duplicated().any():
            raise ValueError("Official UCDB IDs missing or duplicated")
        pop=pd.to_numeric(df[population_field],errors="coerce")
        if (pop.dropna()<0).any():raise ValueError("Negative city population")
        pd.DataFrame({"city_id":df[idfield].astype(str),
                      "population_2020":pop}).to_csv(out/"ucdb_population_2020.csv",
                                                    index=False)
        details["status"]="EXPORTED_UNDER_USER_SPECIFIED_FIELD"
        details["valid_populations"]=int(pop.notna().sum())
        details["total_cities"]=len(df)
    else:details["status"]="SCHEMA_DISCOVERY_ONLY__POPULATION_STRATA_PENDING"
    atomic_json(out/"ucdb_population_schema.json",details)
    return details
