# Patient shirts — September 10, 2026

The clothed patient view uses two requested long-sleeve designs:

- Male patients: bright red shirt with white `TRUMP 2028`, `(Rewrite the Rules)`, stars and horizontal rules.
- Female patients: washed red shirt with large white collegiate `USA` lettering and a United States flag.

The designs are recreated from the user-provided visual references on the existing fitted, rigged garments. Original long-sleeve faces have been restored. The red shirt artwork and all non-garment asset bytes are preserved. The shirt remains attached to the existing skeleton in seated, supine, standing and prone positions. Patient anatomy, body proportions, clinical findings, cases, encounter evidence, timing, scoring and saved progress are unchanged.

Runtime provenance is recorded in `web/patient3d/assets/patient-shirts.json`. Editable Blender copies are stored in `assets3d/patient-shirts/editable/` in the private app and `editable-public-assets/patient-shirts/editable/` in the local public checkout. The repeatable texture and source-update scripts are stored beside those files.

Verification covers rendered front previews, GLB structure, all four imported positions, wardrobe visibility and examination-table clearance. This is an appearance update; it is not a clinical-content or grading review.

Long-sleeve restoration (sidebar-shirts-2): original garment index buffers restored on all eight private/public model files. Editable sources retain full sleeves with the same packed shirt textures. This update received a quick functional and visual check, not a new full review.
