#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 - <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import re
root=Path.cwd();version=(root/'VERSION').read_text().strip()
if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid VERSION')
files=[root/name for name in ('VERSION','projekt.json','pcmonitor.py','README.md','CHANGELOG.md','LICENSE','.start.sh','start-admin.sh')]
for folder in ('modules','assets','lang','help'):
 for p in (root/folder).rglob('*'):
  if p.is_symlink():raise ValueError('Symlink in package: '+str(p))
  if p.is_file() and not any(part.startswith('.') or part=='__pycache__' for part in p.relative_to(root).parts) and p.suffix not in ('.pyc','.log'):files.append(p)
output=root/f'pcmonitor-{version}.zip'
with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=9) as archive:
 for p in sorted(files):archive.write(p,Path('pcmonitor')/p.relative_to(root))
with ZipFile(output) as archive:
 assert archive.testzip() is None
 assert len(archive.namelist())==len(set(archive.namelist()))
print(f'{output} ({len(files)} Dateien), geprüft')
PY
