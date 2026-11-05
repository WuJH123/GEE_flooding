"""Compare independent Gate-C EE 25-band TIFs with ESA official local 10m COG process."""
from __future__ import annotations
import argparse,json,pathlib,numpy as np
from . import worldcover_local_plan as plan

def compare(tiles,reference,out,limit_p95=0.005,limit_max=0.02):
    import rasterio
    from rasterio.windows import from_bounds
    metrics={};errors=[]
    for name,(x0,y0) in plan.FOUR.items():
        base=pathlib.Path(reference)/f'worldcover_{name}_10x10.tif'
        if not base.exists():raise FileNotFoundError('Independent GEE Gate C reference missing: '+str(base))
        with rasterio.open(base) as ref:
            if ref.count!=25 or ref.width!=10 or ref.height!=10:raise ValueError('Gate C reference is not 25-band 10x10')
            comparison=[]
            for a in (0,5):
                for b in (0,5):
                    x,y=x0+a,y0+b
                    native=pathlib.Path(tiles)/f'wc_local_{x}_{y}_5.tif'
                    if not native.exists():raise FileNotFoundError(native)
                    with rasterio.open(native) as cur:
                        if cur.count!=25:raise ValueError('Local native COG missing bands')
                        win=from_bounds(*cur.bounds,transform=ref.transform).round_offsets().round_lengths()
                        if win.width!=5 or win.height!=5:raise ValueError('Native/GEE 10km alignment mismatch')
                        r=ref.read(window=win,masked=True).filled(np.nan)
                        z=cur.read(masked=True).filled(np.nan)
                        both=np.isfinite(z)&np.isfinite(r)
                        if not np.any(both):raise ValueError('Gate C and local have no common values')
                        comparison.extend(np.abs(z[both]-r[both]).tolist())
            p95=float(np.percentile(comparison,95));mx=float(np.max(comparison))
            metrics[name]={'p95_abs_fraction_or_raw_metric':p95,'max_abs_fraction_or_raw_metric':mx}
            if p95>limit_p95 or mx>limit_max:errors.append(name)
    result={'status':'PASS_GATE_C_INDEPENDENT_COMPARISON' if not errors else 'FAIL_GATE_C_NUMERIC_EQUIVALENCE',
            'regions':metrics,'allowed_p95':limit_p95,'allowed_max':limit_max,
            'interpretation':'For WC all bands are dimensionless fractions, so absolute threshold valid.',
            'not_a_validation_of_original_land_cover_labels':True}
    p=pathlib.Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise ValueError('Local/EE Gate C mismatch for '+','.join(errors))
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tiles',required=True);p.add_argument('--reference',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    print(json.dumps(compare(a.tiles,a.reference,a.out),indent=2))
if __name__=='__main__':main()
