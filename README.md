# PCM Practice — free community preview

A local-first CSE practice simulation with24 presentations,48 additional variations and72 written walkthroughs. **Development preview: not clinically validated or study-ready.** The inherited SOAP checker can flag supported statements incorrectly and can give an incorrect repair exercise. Use the course rubric and supervising faculty to assess clinical accuracy; scores are provisional.

## Open the app

Public site: https://skempa7.github.io/pcm-cse-public/

Choose a mode and case, read the doorway/vitals, then enter. During the encounter, **Show anatomy view** reveals the unclothed clinical patient; **Show clothed view** returns. The female anatomical models use the same geometry, skin textures, rig and animation as the original local app. This is a visual option: changing views does not perform an examination or establish clinical findings. Patients start clothed and reload into the clothed view. Detailed vaginal/speculum and rectal inspection modules remain excluded. No arousal effects or sexualized clothing are included.

The public cohort contains18 women and6 men, all authored adults. Male models are bald with an adapted torso and human skin. The current male derivative still has residual chest contour and needs a better male body asset. The male body is an approximate derivative; it is not a validated male genital-anatomy model. This is a limited fictional practice cohort, not representative clinical or demographic coverage.

## No billable application services

The app has **no API key, paid AI module, hosted application server, payment integration, telemetry, Git LFS or custom paid build runner**. GitHub Pages serves static files. The Python encounter engine runs inside the visitor's browser using bundled Pyodide. Speech uses the browser/device default voice; optional speech recognition may use the browser vendor's service, with no app-owner credentials.

Visitors cannot spend the app creator's OpenAI balance through this build: that service and its credentials are absent. GitHub Pages for public repositories is available with GitHub Free and has usage limits; throttling or suspension can occur at those limits. No metered hosting fallback has been configured. Provider policies may change; this project does not enroll in paid services or auto-upgrade anything.

## Progress, timing and privacy

Work remains in IndexedDB/localStorage in the visitor's browser. There is no account or cross-device sync; clearing site data deletes local work. One active tab per origin prevents competing writes. GitHub receives normal static-page requests, but the app does not upload interviews, notes or scores to its creator.

The encounter is14 minutes and SOAP9 minutes. Practice adds a labeled2-minute organization interval; course rehearsal does not. Guided mode is untimed and uses accelerated examination actions. Reload retains absolute deadlines and saved work. Opening a walkthrough during an active independent/rehearsal attempt requires converting it to assisted practice. This is client-side practice software, not a secure/proctored exam platform.

## Run and edit locally

Use a current Chrome, Edge, Firefox or Safari browser. From this repository:

```
python3 -m http.server 8773 --bind 127.0.0.1
```

Open http://127.0.0.1:8773/web/. Do not open index.html directly from the filesystem; module workers and persistent browser storage need an HTTP(S) origin.

- `pcmcse/`, `offline_routes.py`: provider-free Python engine, authored case data and lessons.
- `web/engine-worker.mjs`, `web/public-runtime.js`: browser worker, persistent storage and local request adapter.
- `web/patient3d/src/`: Babylon.js integration. `package-lock.json` pins dependencies; run `npm ci` and `npm run build` in that folder to rebuild its bundle.
- Editable Blender5.2.1 source scenes are delivered locally to the creator. Public glTF assets in `web/patient3d/assets/` can also be imported into Blender; no proprietary trial content is required.
- `tools/package_engine.py`: regenerate `web/engine.zip` after Python or case edits.
- `tools/build_teaching_library.py`: regenerate lessons using the actual encounter engine, against an isolated temporary database.
- `tools/validate_female_glb_parity.py`: compare the three female GLBs against the original export. Geometry, textures, rig, skinning and animation must match exactly; only wardrobe node names may differ.
- `tools/test_public_release.py`: run72 route/workflow regression paths plus timing, locked notes, assistance gates and asset checks. These are structural tests, not medical validation.
- `tools/export_public_patients.py`: repeat the asset conversion with Blender5.2.1 and `PCM_PRIVATE_ASSETS` pointing to a locally held original MPFB asset source and `PCM_PRIVATE_GLBS` to the original `web/patient3d/assets` directory. Female GLBs preserve the original binary payload exactly; only wardrobe node names change. The source scenes are never overwritten. Existing editable public scenes can be edited and re-exported without the private app or proprietary tools.

## Accuracy and limitations

Written walkthroughs are synthesized teaching examples tied to each case's evidence, not official station answers. The broader clinical-readiness review previously failed; public hosting does not change that result. Specific limitations include false unsupported-documentation flags, occasional scripted question misunderstandings, approximate mouth movement rather than accurate lip synchronization, basic model/cloth deformation, and limited anatomy. The system cannot assess palpation, tissue resistance, exact anatomical landmarks or hands-on technique.

Source-course files, the creator's saved attempts, private backend/credentials are not included. The existing licensed clinical character geometry is included for anatomical education. Source titles/locators document curriculum provenance without publishing private course PDFs, manuals or lecture files. This is independent student practice software, not an official institutional examination or medical-care tool.

Third-party licensing and source attribution: [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Application-specific code/content retains its existing author's rights; third-party assets retain their own licenses.
