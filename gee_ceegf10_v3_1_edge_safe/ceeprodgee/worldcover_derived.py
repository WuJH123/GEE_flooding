"""Derive publication-readable class combinations from existing 25 bands.

No GEE computation. Definitions are declared before predictive modeling.
"""
import numpy as np
from .contract import WC_CODES

COMPOSITES={
    'wc_green_noncrop_fraction_land':(10,20,30,90,95),
    'wc_vegetated_with_crops_fraction_land':(10,20,30,40,90,95),
    'wc_wetland_fraction_land':(90,95),
    'wc_built_fraction_land':(50,),
    'wc_surface_water_fraction_land':(80,),
    'wc_green_noncrop_fraction_fullcell':(10,20,30,90,95),
    'wc_wetland_fraction_fullcell':(90,95),
    'wc_built_fraction_fullcell':(50,),
    'wc_surface_water_fraction_fullcell':(80,),
}

def derive(frame):
    """Only assign an aggregate if all participating source categories are finite."""
    for name,codes in COMPOSITES.items():
        suffix='land' if name.endswith('_land') else 'fullcell'
        names=[f'wc_{c}_fraction_{suffix}' for c in codes]
        if not set(names).issubset(frame.columns):
            raise ValueError('Required ESA source categories missing for '+name)
        frame[name]=frame[names].sum(axis=1,min_count=len(names))
        if not (frame[name].dropna().between(-1e-5,1.00001)).all():
            raise ValueError('Derived WorldCover fractions outside [0,1]')
    return frame


def main():
    import argparse,pandas as pd,pathlib,json
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();out=pathlib.Path(a.output)
    if out.exists():raise FileExistsError(out)
    df=pd.read_parquet(a.input)
    if 'grid_id' not in df:raise ValueError('No frozen grid_id')
    result=derive(df)
    out.parent.mkdir(parents=True,exist_ok=True)
    result.to_parquet(out,index=False)
    out.with_suffix('.qc.json').write_text(json.dumps({'status':'DERIVED_FROM_11_NATIVE_CLASSES_NO_GEE', 'n_rows':len(result),'columns':list(COMPOSITES)},indent=2))
if __name__=='__main__':main()
