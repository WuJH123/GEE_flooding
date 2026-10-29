"""Project separation and filesystem write guards."""
from pathlib import Path
import json

DEFAULT_ROOT = Path(r'E:\GEE_flooding')

def resolve_root(value):
    return Path(value).expanduser().resolve()

def safe_output(root, relative):
    root = resolve_root(root)
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f'Refusing write outside project root: {target}')
    return target

def ensure_structure(root):
    root = resolve_root(root)
    for p in ('data/raw', 'data/derived', 'outputs/labels', 'outputs/panels',
              'outputs/models', 'outputs/figures', 'reports/qc', 'logs', 'cache'):
        safe_output(root, p).mkdir(parents=True,exist_ok=True)
    return root

def atomic_json(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.partial')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    tmp.replace(path)

def check_raw_groundsource(path):
    """Reject old grid-day aggregates misrepresented as raw Groundsource."""
    path=Path(path)
    if not path.is_file():raise FileNotFoundError(path)
    import pyarrow.parquet as pq
    names=set(pq.ParquetFile(path).schema_arrow.names)
    required={'uuid','geometry','start_date','end_date','area_km2'}
    missing=required-names
    if missing:
        raise ValueError(f'Not original Groundsource; missing {sorted(missing)}: {path}')
    return path
