#!/usr/bin/env python3
"""Verify delivered external-female GLB identity, facial controls and pose coverage.
Usage: python3 tools/verify_female_external.py [project-root]
Does not access preferences, saved attempts, services, or credentials.
"""
import sys,json,struct,hashlib
from pathlib import Path
root=Path(sys.argv[1])if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
assets=root/'web/patient3d/assets';manifest=json.loads((assets/'female-external-surface.json').read_text());reports=[]
for item in manifest['runtime_assets']:
 p=assets/item['file'];raw=p.read_bytes();size=struct.unpack_from('<I',raw,12)[0];j=json.loads(raw[20:20+size]);digest=hashlib.sha256(raw).hexdigest()
 assert digest==item['sha256'],(p.name,'hash changed')
 assert len(raw)<100_000_000
 body=next(n for n in j['nodes']if n.get('name')in ('PCM_FemaleBody','PCM_AnatomicalBody'))
 mesh=j['meshes'][body['mesh']];assert len(mesh['primitives'])==1
 primitive=mesh['primitives'][0]
 assert j['accessors'][primitive['attributes']['POSITION']]['count']==14668
 assert j['accessors'][primitive['indices']]['count']==27020*3
 assert j['materials'][primitive['material']]['name']=='PCM_Mat_Skin'
 assert mesh['extras']['targetNames']==['Blink','Speech','Warmth','Concern','Discomfort']
 assert {a['name']for a in j['animations']}=={'PCM_Seated','PCM_Supine','PCM_Standing','PCM_Prone'}
 assert not any('external'in n.get('name','').lower()for n in j['nodes'])
 reports.append({'file':p.name,'sha256':digest,'bytes':len(raw),'passed':True})
print(json.dumps({'passed':True,'assets':reports,'scope':'Identity and GLB structural validation; clinical and live-browser review are separate.'},indent=2))
