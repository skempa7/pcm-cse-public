"""Convert retained MHX2 CC0 extra-content anatomy to MPFB's fitting format.

Usage: python3 convert_male_external_mxa.py PATH_TO_PENIS_MXA OUTPUT_DIRECTORY
The original file and the original author's license clarification must accompany
the editable source. This converts asset data; it does not import MHX2 code.
"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mxa', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
data = json.loads(args.mxa.read_text())
if data.get('uuid') != '4af5093b-aabe-4ed8-9476-b81272b9fba0':
    raise ValueError('Use the retained first MHX2 penis.mxa asset; another file requires independent review.')
out = args.output
out.mkdir(parents=True, exist_ok=True)
mesh = data['mesh']
rows = ['# MHX2 added-content external adult anatomy; CC0 per original author.']
rows += ['v ' + ' '.join(map(str, v)) for v in mesh['vertices']]
rows += ['vt ' + ' '.join(map(str, v)) for v in mesh['uv_coordinates']]
rows += ['f ' + ' '.join(f'{v+1}/{u+1}' for v, u in zip(face, uv))
         for face, uv in zip(mesh['faces'], mesh['uv_faces'])]
(out / 'male_external_neutral.obj').write_text('\n'.join(rows) + '\n')
proxy = data['proxy']
rows = ['# CC0 MHX2 added content: Thomas Larsson; see retained provenance.',
        'name male_external_neutral', 'uuid ' + data['uuid'], 'basemesh hm08',
        'obj_file male_external_neutral.obj', 'z_depth 31',
        'material male_external_neutral.mhmat']
rows += [axis + '_scale ' + ' '.join(map(str, proxy['bounding_box'][axis]))
         for axis in ('x', 'y', 'z')]
rows += ['verts 0']
for ids, weights, offsets in proxy['fitting']:
    rows.append(' '.join(map(str, ids + weights + offsets)))
rows += ['delete_verts']
rows += [str(i) for i, deleted in enumerate(proxy['delete_verts']) if deleted]
(out / 'male_external_neutral.mhclo').write_text('\n'.join(rows) + '\n')
(out / 'male_external_neutral.mhmat').write_text(
    'name Neutral male external skin\ndiffuseColor 0.58 0.39 0.31\n')
print(f"Converted {len(mesh['vertices'])} vertices and {len(mesh['faces'])} faces.")
