"""Export the original female clinical patient views without replacing human skin.
Female runtime GLBs retain the exact original binary payload (geometry, skin,
textures, morphs, skeleton and animation). Only public wardrobe node names change.
The original MPFB source scenes and runtime assets are opened read-only.
Set PCM_PRIVATE_ASSETS to the original MPFB source directory and PCM_PRIVATE_GLBS
to its already-exported patient3d/assets directory. No trial assets are used.
Male patients are built separately from male MPFB macro controls with
build_mpfb_male.py. This exporter never derives a male from a female scene.
"""
from pathlib import Path
import bpy, json, os, struct
ROOT = Path(__file__).resolve().parents[1]
if os.environ.get('PCM_PUBLIC_MALE_ONLY'):
    raise SystemExit('The female-to-male conversion is retired. Use tools/build_mpfb_male.py and its male posture export instructions.')
SOURCE = Path(os.environ['PCM_PRIVATE_ASSETS'])
RUNTIME = Path(os.environ['PCM_PRIVATE_GLBS'])
OUT = ROOT / 'web/patient3d/assets'; OUT.mkdir(parents=True, exist_ok=True)
EDIT = ROOT / 'editable-public-assets'; EDIT.mkdir(exist_ok=True)

NODE_NAMES={'PCM_FemaleBody':'PCM_AnatomicalBody',
 'PCM_FemaleBody_Covered':'PCM_PublicBody','PCM_FittedKnit':'PCM_PublicKnit',
 'PCM_FittedCasual':'PCM_PublicTrousers','PCM_Sneakers':'PCM_PublicShoes'}

def copy_female_runtime(build):
 source=RUNTIME/('mpfb-female-'+build+'.glb')
 data=source.read_bytes();length,kind=struct.unpack_from('<II',data,12)
 assert data[:4]==b'glTF' and kind==0x4e4f534a
 doc=json.loads(data[20:20+length])
 for node in doc['nodes']:
  if node.get('name') in NODE_NAMES:node['name']=NODE_NAMES[node['name']]
 payload=json.dumps(doc,separators=(',',':')).encode();payload+=b' '*((-len(payload))%4)
 binary=data[20+length:]
 out=struct.pack('<4sII',b'glTF',2,20+len(payload)+len(binary))+struct.pack('<II',len(payload),kind)+payload+binary
 (OUT/('public-female-'+build+'.glb')).write_bytes(out)
 print('EXACT_FEMALE_RUNTIME',build,flush=True)

for build in ('short-slender', 'standard', 'tall-full'):
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE / 'variants' / build / 'MPFB-female-patient.blend'))
    for old, new in NODE_NAMES.items():
        bpy.data.objects[old].name = new
    bpy.ops.wm.save_as_mainfile(filepath=str(EDIT / ('public-female-' + build + '.blend')))
    copy_female_runtime(build)
