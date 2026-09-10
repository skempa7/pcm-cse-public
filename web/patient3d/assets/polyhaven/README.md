# Clinical room materials

These are optimized derivatives of the user's installed **Poly Haven Starter Library**. They are CC0 assets; no paid browsing add-on or purchase is involved. Exact original paths and SHA-256 hashes are in `manifest.json`.

Source pages: [Studio Small 03](https://polyhaven.com/a/studio_small_03), [Painted Plaster Wall](https://polyhaven.com/a/painted_plaster_wall), [Wood Table 001](https://polyhaven.com/a/wood_table_001), [Fabric Pattern 07](https://polyhaven.com/a/fabric_pattern_07). [Poly Haven license](https://polyhaven.com/license).

The editable original material library is `Local Poly Haven asset library (see SOURCES.txt)`. This export leaves that file and all downloaded originals untouched.

Run from the app project root:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --python tools/prepare_polyhaven_assets.py
```

The script uses Blender image IO to prepare 1024-pixel sRGB albedo maps, 512-pixel linear OpenGL normal maps, 512-pixel linear packed roughness maps, and a 1024 × 512 linear HDR panorama. The albedo derivatives preserve scanned luminance variation but use documented clinical palettes: clean warm plaster, natural oak, and pale sage fabric. This avoids presenting the original weathered plaster and red checked fabric as a clean clinical setting. Roughness occupies the green channel, metalness is zero, and the occlusion channel is neutral. No displacement geometry is added. Normal maps are deliberately saved as 8-bit PNGs to avoid shipping unnecessary 16-bit data.

`src/clinical-environment.js` loads these files after the room model. It uses the HDR as prefiltered image-based lighting with 128-pixel cubemap faces, without placing a photographic backdrop in the clinical room. Textured plaster is assigned to the existing walls, wood to the hinged door and cabinetry, and fabric to the pillow and towel. The exam mattress retains its original material. Superseded procedural grain strips are hidden only after the scanned wood loads successfully. Patient skin, eyes, hair, clothing, pose, camera paths, and clinical state are not changed by this module. Lights become neutral soft daylight after the environment loads successfully. The original materials and light setup remain fallbacks for failed resources.

The derivatives total **4,175,006 bytes** before HTTP compression. The nine image maps require approximately 24 MiB of GPU storage if uploaded as RGBA8 with mipmaps; environment and temporary HDR conversion allocations are additional. This is an allocation estimate, not a measured device performance result. The module reports actual initialization duration and resource failures in `scene.metadata.clinicalEnvironment` for the app's renderer diagnostics. Running-app appearance and frame rate must be checked independently.

This room layer is decorative. It releases no examination findings and creates no clinical evidence.
