# Third-party notices

- **Pyodide 314.0.6** — Mozilla Public License 2.0. Unmodified core browser distribution from https://github.com/pyodide/pyodide/releases/tag/314.0.6. Corresponding source: https://github.com/pyodide/pyodide/tree/314.0.6. License: `licenses/PYODIDE-LICENSE.txt`. The local engine wrapper and authored Python package are separate application code.
- **CPython** (included in the Pyodide runtime) — PSF License and associated notices: `licenses/PYTHON-LICENSE.txt`. Source: https://github.com/python/cpython/tree/3.14.
- **Babylon.js core/loaders 9.25.0** — Apache License2.0, Microsoft Corporation. Full notice: `web/patient3d/THIRD-PARTY-NOTICES.txt`. Source: https://github.com/BabylonJS/Babylon.js/tree/9.25.0.
- **MakeHuman/MPFB core body, eyes, brows, teeth, tongue, skin and core casual clothes/shoes** — MakeHuman Community/MakeHuman Team, CC0 asset license. `licenses/MAKEHUMAN-ASSETS.md`; https://static.makehumancommunity.org/about/license.html. Modified fitting, skeleton export, facial morphs and clinical wardrobe switching. The current male is generated directly from the adult male macro base with CC0 young-adult male skin and male casual trousers. No MakeHuman or MPFB add-on application code is redistributed.
- **Elvs Hazel Hair**, Elvaerwyn — CC-BY, as declared in the original asset header (version unspecified). Source: http://www.makehumancommunity.org/node/2816. Changes: fitting, subdivision, skin weights, material conversion and color variants. Author credit remains required. Original header: `licenses/HAIR-ATTRIBUTION.txt`.
- **Toigo fisherman sweater**, MRT — CC0 as declared in source asset; http://www.makehuman.org/. Modified fitting/material conversion.
- **Poly Haven** lighting and plaster/wood/fabric maps — CC0. Asset URLs, authors and derived-map descriptions: `web/patient3d/assets/polyhaven/SOURCES.txt` and `manifest.json`; https://polyhaven.com/license. The clinical table and added decorations are project-created. The imported room geometry and supplied wood textures have separate provenance and license limitations in `licenses/SUPPLIED-ROOM.md`.

No proprietary Human Generator trial content is included. No purchased assets or paid browser-asset services are required. Local editable files preserve original asset provenance. The supplied room is not covered by the CC0 licenses listed above.

## External anatomical surfaces

The neutral external penile/scrotal and vulvar surfaces use MHX2 added content by Thomas Larsson, adapted to the adult MPFB bodies. Source data: https://github.com/makehumancommunity/mhx2-makehuman-exchange/tree/master/import_runtime_mhx2/data/hm8/genitalia. The original author's explicit release of extra imported content under CC0 is at https://thomasmakehuman.wordpress.com/license-information/. Some retained source data carries older AGPL metadata; the later explicit content release is the licensing basis, and the original metadata is preserved in the local editable packages. MHX2 importer application code is not redistributed. Changes include fitting, welding, skinning, material/UV integration and exclusion from the clothed mesh. These are external educational surface approximations, with no internal examination module or soft-tissue simulation.

## Printable walkthrough photography

- **Stethoscope**, HujiStat — author public-domain dedication. Source: https://commons.wikimedia.org/wiki/File:Stethoscope-2.jpg. Local file: `web/print-assets/stethoscope.jpg`.
- **Sphygmomanometer and stethoscope**, CDC; Wikimedia color correction by Jacek Halicki — public-domain U.S. government work. Source: https://commons.wikimedia.org/wiki/File:Sphygmomanometer.jpg. Local file: `web/print-assets/blood-pressure-equipment.jpg`.
- Patient-room screenshots were captured in the running Chat CSE application. The underlying MakeHuman, hair and Poly Haven notices above continue to apply. Reused illustrative patients are labeled as representative in the walkthrough.

Exact image URLs and file hashes are in `web/print-assets/ONLINE-SOURCES.json` and `APP-SOURCES.json`. Equipment photographs and patient screenshots do not supply diagnostic findings.
