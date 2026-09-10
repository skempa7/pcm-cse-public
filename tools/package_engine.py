from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
with zipfile.ZipFile(ROOT/'web/engine.zip','w',zipfile.ZIP_DEFLATED) as z:
 z.write(ROOT/'offline_routes.py','offline_routes.py')
 for p in sorted((ROOT/'pcmcse').rglob('*')):
  if p.is_file() and p.suffix in ('.json','.py'):z.write(p,str(p.relative_to(ROOT)))
print('Bundled provider-free browser engine')
