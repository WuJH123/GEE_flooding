"""Allow repository-root pytest to import standalone GF10 server HPC package."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
