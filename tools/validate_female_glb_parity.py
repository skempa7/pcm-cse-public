#!/usr/bin/env python3
"""Verify private/public female GLBs differ only by explicit mesh/node names.

Usage: python3 validate_female_glb_parity.py PRIVATE_ASSETS PUBLIC_ASSETS
No files are changed. The JSON report goes to stdout. Optional --rename arguments
extend the accepted old=new node/mesh name map, never other JSON properties.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

DEFAULT_RENAMES = {
    'PCM_FemaleBody': {'PCM_AnatomyManikin', 'PCM_AnatomicalBody', 'PCM_AnatomyBody'},
    'PCM_FemaleBody_Anatomy': {'PCM_AnatomyManikin', 'PCM_AnatomicalBody', 'PCM_AnatomyBody'},
    'PCM_FemaleBody_Covered': {'PCM_PublicBody'},
    'PCM_FemaleBody_Covered_Anatomy': {'PCM_PublicBody'},
    'PCM_FittedKnit': {'PCM_PublicKnit'},
    'PCM_FittedCasual': {'PCM_PublicTrousers'},
    'PCM_Sneakers': {'PCM_PublicShoes'},
}


def parse_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', data)
    assert magic == 0x46546C67 and version == 2 and length == len(data)
    chunks = []
    pos = 12
    while pos < length:
        size, kind = struct.unpack_from('<II', data, pos)
        pos += 8
        chunks.append((kind, data[pos:pos+size]))
        pos += size
    assert pos == length and chunks[0][0] == 0x4E4F534A
    return data, json.loads(chunks[0][1]), chunks[1:]


def compare(source, target, renames):
    s_bytes, sj, sc = parse_glb(source)
    t_bytes, tj, tc = parse_glb(target)
    differences = []
    for group in ('nodes', 'meshes'):
        if len(sj.get(group, [])) != len(tj.get(group, [])):
            continue  # Deep comparison below catches additions/removals.
        for i, (a, b) in enumerate(zip(sj.get(group, []), tj.get(group, []))):
            if a.get('name') != b.get('name'):
                differences.append({'path': '%s[%s].name' % (group, i),
                                    'from': a.get('name'), 'to': b.get('name')})
                if b.get('name') in renames.get(a.get('name'), set()):
                    b['name'] = a['name']
    binary_equal = sc == tc
    json_equal = sj == tj
    body = next(m for m in sj['meshes'] if m['name'] == 'PCM_FemaleBody_Anatomy')
    return {
        'build': source.stem,
        'passed': binary_equal and json_equal,
        'binary_chunks_exactly_equal': binary_equal,
        'json_exactly_equal_after_allowlisted_names': json_equal,
        'source_sha256': hashlib.sha256(s_bytes).hexdigest(),
        'public_sha256': hashlib.sha256(t_bytes).hexdigest(),
        'binary_sha256': [hashlib.sha256(chunk).hexdigest() for _, chunk in sc],
        'name_changes': differences,
        'body_vertices': [sj['accessors'][p['attributes']['POSITION']]['count'] for p in body['primitives']],
        'facial_targets': body.get('extras', {}).get('targetNames'),
        'animation_clips': [a.get('name') for a in sj.get('animations', [])],
        'joint_count': [len(s['joints']) for s in sj.get('skins', [])],
        'proof_scope': 'Exact binary and JSON parity covers geometry, UVs, textures, materials, skin weights, skeleton, facial targets and animation clips. It does not independently validate anatomical or clinical accuracy.'
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_assets', type=Path)
    p.add_argument('public_assets', type=Path)
    p.add_argument('--rename', action='append', default=[])
    args = p.parse_args()
    renames = {k: set(v) for k, v in DEFAULT_RENAMES.items()}
    for item in args.rename:
        old, new = item.split('=', 1)
        renames.setdefault(old, set()).add(new)
    result = [compare(args.private_assets / ('mpfb-female-' + build + '.glb'),
                      args.public_assets / ('public-female-' + build + '.glb'), renames)
              for build in ('short-slender', 'standard', 'tall-full')]
    print(json.dumps({'passed': all(r['passed'] for r in result), 'assets': result}, indent=2))
    return 0 if all(r['passed'] for r in result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
