"""Restore archived input paths required by historical data checks; never overwrite differences."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[2]
source = Path(__file__).resolve().parent / 'source-inputs'
target = ROOT / 'jobs/new_scenarios/source'
files = sorted(p for p in source.rglob('*') if p.is_file())
for p in files:
    dest = target / p.relative_to(source)
    if dest.exists() and dest.read_bytes() != p.read_bytes():
        raise SystemExit('Refusing to overwrite different input: ' + str(dest))
for p in files:
    dest = target / p.relative_to(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(p, dest)
print('Restored', len(files), 'archived source files; no API calls.')
