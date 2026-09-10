# Female patient proportions — September 10, 2026

The female patient meshes now use a moderate C-cup-inspired appearance and a slimmer waist. Cup letters depend on band size; this is a visual proportion, not a measured bra fitting. The local waist taper peaks at 10%, and the restrained anterior bust adjustment peaks near 1.8 cm. The body and matching knit/trousers receive the same smooth deformation. Existing differences in height and body build remain.

Faces, hair, hips, skeletal proportions, external anatomy, texture data, facial morphs and all four animation clips are retained. The female prone table contour is fitted to the changed torso. The male model, case data, timers, encounter evidence, SOAP grading and saved attempts are not changed by this update.

The three public female assets have the same binary geometry, material, rig and animation data as their private counterparts; only the existing public mesh names differ. The private legacy/base female model is updated as well.

## Editable sources and repeatable generation

The local editable delivery is in `assets3d/female-proportions/` for the private app and `editable-public-assets/female-proportions/` for the public checkout. It includes `.blend` files, the shared deformation field, build scripts and hash reports. The public editable package stays local; browser-ready GLBs are published.

To reproduce without applying the deformation twice:

1. Use the pre-adjustment files in the private app's `assets3d/female-external/editable/` as Blender inputs. Retain the pre-adjustment private/public runtime GLBs from the delivery backup (or public parent revision).
2. Create an output directory with a `reports/` subdirectory. Run Blender with `--factory-startup -b --python tools/build_female_shape_sources.py -- ORIGINAL_BLEND_DIRECTORY OUTPUT_DIRECTORY/editable`.
3. Run `python3 tools/build_female_shape_glbs.py ORIGINAL_PRIVATE_ROOT ORIGINAL_PUBLIC_ROOT OUTPUT_DIRECTORY`. This applies the same field to the original GLB bind positions and normals, keeping unrelated binary data exact. It intentionally avoids a fresh export that could alter existing animation data.
4. Use the included fitted `clinical-table.js` and updated support hashes. Bundle `src/room.js` with the project's pinned esbuild/Babylon dependencies. Refresh the asset cache tags when delivering new files.

## Verification scope

Basic checks cover imported GLBs, four patient positions, clothing visibility, table clearance, preserved rig/animation/morph data, public/private asset parity, JavaScript syntax and production bundles. Independent review was skipped at the user's request. No new visual-quality score, clinical validation or whole-app readiness claim is made by this asset update.
