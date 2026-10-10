from pathlib import Path
import os,hashlib,subprocess,shutil,gzip,json
root=Path(__file__).resolve().parent.parent
import tempfile
build_parent=root/'dist'
build_parent.mkdir(exist_ok=True)
if not build_parent.is_dir() or build_parent.is_symlink(): raise SystemExit('Beauftragter Ausgabeordner dist fehlt oder ist verlinkt.')
work=Path(tempfile.mkdtemp(prefix='pcmonitor-deb-',dir=build_parent))
stage=work/'paket';stage.mkdir()
version=(root/'VERSION').read_text().strip()
import re
if not re.fullmatch(r'\d+\.\d+\.\d+', version): raise SystemExit('Ungültige VERSION')
app=stage/'usr/share/pcmonitor';app.mkdir(parents=True)
files=[root/n for n in ('pcmonitor.py','VERSION','projekt.json')]
for folder in ('modules','assets','lang','help'):
 for p in sorted((root/folder).rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc',): files.append(p)
manifest={}
for src in files:
 assert src.is_file() and not src.is_symlink()
 rel=src.relative_to(root);dst=app/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);manifest[str(rel)]=hashlib.sha256(src.read_bytes()).hexdigest()
doc=stage/'usr/share/doc/pcmonitor';doc.mkdir(parents=True)
shutil.copyfile(root/'LICENSE',doc/'copyright')
for name in ['README.md','CHANGELOG.md']:
 (doc/(name+'.gz')).write_bytes(gzip.compress((root/name).read_bytes(),mtime=0))
binpath=stage/'usr/bin/pcmonitor';binpath.parent.mkdir(parents=True)
binpath.write_text('#!/bin/sh\nunset PYTHON_TEMPLATE_DEV PCMONITOR_ADMIN_QUERY\nexec /usr/bin/python3 -B /usr/share/pcmonitor/pcmonitor.py "$@"\n')
adminpath=stage/'usr/bin/pcmonitor-admin'
adminpath.write_text('#!/bin/sh\nunset PYTHON_TEMPLATE_DEV\nexport PCMONITOR_ADMIN_QUERY=1\nexec /usr/bin/python3 -B /usr/share/pcmonitor/pcmonitor.py "$@"\n')
apps=stage/'usr/share/applications';apps.mkdir(parents=True)
import sys
sys.path.insert(0,str(root/'packaging'))
from desktop_lifecycle import desktop_entry
for admin in (False,True):
 (apps/('pcmonitor-admin.desktop' if admin else 'pcmonitor.desktop')).write_text(desktop_entry(admin))

for p in stage.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
binpath.chmod(0o755)
adminpath.chmod(0o755)
cleanup=stage/'usr/bin/pcmonitor-cleanup'
shutil.copyfile(root/'packaging/desktop_lifecycle.py',cleanup)
cleanup.chmod(0o755)
control=stage/'DEBIAN';control.mkdir()
size=sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
(control/'control').write_text(f'''Package: pcmonitor
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: Josef
Installed-Size: {(size+1023)//1024}
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.8), python3-bs4, python3-requests, util-linux, lshw, dmidecode, pciutils, iproute2, pkexec
Recommends: iw, x11-xserver-utils, pulseaudio-utils
Description: Read-only PC hardware inventory with GTK 4
 Displays hardware details and exports inventory reports.
 Includes German and English user interfaces and offline help.
''')
(control/'md5sums').write_text(''.join(f'{hashlib.md5(p.read_bytes()).hexdigest()}  {p.relative_to(stage)}\n' for p in sorted(stage.rglob('*')) if p.is_file() and control not in p.parents))
for p in control.iterdir():p.chmod(0o644)
for hook in ('postinst','prerm','postrm'):
 dst=control/hook
 source=(root/'packaging/desktop_lifecycle.py').read_text()
 if hook=='postinst': source=source.replace("action not in ('configure', 'remove', 'purge')", "action != 'configure'")
 elif hook=='prerm': source=source.replace("action not in ('configure', 'remove', 'purge')", "action not in ('remove', 'purge')")
 else: source=source.replace("action not in ('configure', 'remove', 'purge')", "action != 'purge'")
 dst.write_text(source);dst.chmod(0o755)
(work/'manifest.json').write_text(json.dumps(manifest,indent=2))
output=root/'dist'/f'pcmonitor_{version}_all.deb'
output.parent.mkdir(exist_ok=True)
if output.exists():
 backup=root/'dist'/f'pcmonitor_{version}_all-vor-reparatur.deb'
 if not backup.exists(): shutil.copy2(output,backup)
subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(output)],check=True)
subprocess.run(['dpkg-deb','--info',str(output)],check=True,stdout=subprocess.DEVNULL)
shutil.rmtree(work)
print(output)
