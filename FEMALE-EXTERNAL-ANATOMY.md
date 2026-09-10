# Female external anatomical surface

The existing female patient models now have a neutral external vulvar surface in their anatomical view. The clothed view is unchanged. This is a surface approximation for orientation, not a patient-specific finding or a simulation of a genital examination. It adds no encounter evidence, scoring criteria, pathology, sexual-response state, internal vaginal canal, speculum interaction, or rectal examination. The previously parked internal-examination modules remain excluded.

## Asset and license provenance

- Source: Thomas Larsson, **MHX2 extra content**, `import_runtime_mhx2/data/hm8/genitalia/vulva.mxa`, from the [official MakeHuman Community repository](https://github.com/makehumancommunity/mhx2-makehuman-exchange/tree/master/import_runtime_mhx2/data/hm8/genitalia).
- Original SHA-256: `1f2f344d4fd1ede034eb905d071e50de0dd72154b502550b5a046429895df2bd`.
- License basis: the [author's license-information page](https://thomasmakehuman.wordpress.com/license-information/) separately releases MHX2-added content under [CC0](https://creativecommons.org/publicdomain/zero/1.0/). Checked September 10, 2026. Importer software has a separate GPL license and is not redistributed here.
- The retained `vulva.mxa` has an older **AGPL3 metadata field**. That original field is preserved, not rewritten. The author’s explicit CC0 release of extra content is the redistribution basis; the metadata does not itself say CC0. No restricted Human Generator trial content was used.
- The preexisting MPFB body/skin/hair/clothing retain their existing asset provenance. The adapted external surface uses the patient's existing `PCM_Mat_Skin`; it adds no image textures.

The [NCI/SEER external-genitalia anatomy reference](https://training.seer.cancer.gov/anatomy/reproductive/female/genitalia.html) was used to distinguish external vulvar structures from the vagina. It is an orientation reference; it does not validate this mesh's dimensions or make the model suitable for diagnosis or a hands-on skill assessment. External folds are approximated; individual anatomy varies, and internal openings/tissue mechanics are not represented as examination-capable anatomy.

## What changed and what was preserved

The original fitted body contains 13,380 native vertices. The external asset has 181 vertices and 168 faces and supplies a native-source deletion mask. Fitting replaces 36 local body faces; 24 boundary vertices are welded. The finished anatomical body has 13,512 native vertices and 13,510 faces, exported as 14,668 UV-split vertices and 27,020 triangles.

The export packager appends only the replacement anatomical primitive to each existing GLB. It retains the original binary prefix and exact JSON for every non-anatomical mesh, node, skin, animation, texture, material, and scene. Of 14,517 original exported body positions, 14,499 remain unchanged. Facial targets Blink, Speech, Warmth, Concern, and Discomfort remain present. The seated, supine, standing, and prone clips remain byte-for-byte unchanged. Public female counterparts differ from private only by the existing allowlisted mesh and node names.

There is no separately visible external mesh that can leak through clothing: the surface is joined into the existing anatomical-body target. The covered body and clothes are unchanged. No JavaScript visibility, examination, timing, evidence, or grading code was changed by this asset work.

## Editable files and repeatable build

Local delivery packages are `assets3d/female-external/` in the private edition and `editable-public-assets/female-external/` in the public checkout. The public editable package is local-only and excluded from Git. Each includes:

- `editable/`: updated `.blend` files with the existing rig, clothes, facial controls, and four poses.
- `originals/`: prior `.blend` and GLB files for a reproducible baseline and rollback.
- `external-source/original/vulva.mxa`: unmodified licensed source.
- `external-source/`: converted OBJ, MHCLO, and placeholder material; the actual export uses the existing patient skin.
- `tools/`: repeatable conversion, fitting, and GLB-preserving packaging scripts.
- `reports/`: exact source/export hashes, preserved-data checks, and pose-import results.

Use Blender **5.2.1** and the installed MPFB **2.0.17**. Set `PCM_MPFB_ADDON` to your installed MPFB directory. The script uses a temporary add-on import shim; it does not download files or install a paid service. Start with the retained original source, not an already modified body:

```bash
python3 tools/convert_external_mxa.py external-source/original/vulva.mxa external-source
export PCM_MPFB_ADDON='/path/to/installed/mpfb'
/Applications/Blender.app/Contents/MacOS/Blender --background --python tools/fit_female_external.py -- originals/mpfb-female-standard.blend build/standard external-source/female_external_neutral.mhclo
python3 tools/graft_female_glb.py originals/mpfb-female-standard.glb build/standard/anatomical-body.glb build/standard/mpfb-female-standard.glb build/standard/graft-report.json
```

Repeat for `short-slender` and `tall-full`, plus `patient` in the private edition. To retain public names without changing any binary content:

```bash
python3 tools/derive_public_female.py build/standard/mpfb-female-standard.glb originals/public-female-standard.glb build/standard/public-female-standard.glb
```

The importer package has no runtime role. Runtime files are local GLBs, below 18 MB each; no external requests, credentials, usage billing, or paid dependencies are added.

## Verification boundaries

Completed checks: all four private GLBs import successfully in Blender; all four pose actions skin to finite geometry; standard-body imported renders were inspected in seated, supine, standing, and prone positions. The local external patch was inspected from front and lower-oblique views for continuity. Source-to-GLB preservation and exact three-pair private/public parity passed.

The body-only inspection renders deliberately hide other meshes to expose deformation; that does not mean hair, eyes, clothes, or room assets were removed from the application. Runtime browser appearance, wardrobe switching, pose transitions, room support, and independent usability assessment are checked in the main build review. These asset checks alone do not establish clinical accuracy of the whole case library or readiness of the entire app.
