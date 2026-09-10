# Chat CSE — free community preview

## Student portal and print update — September 10, 2026

Home brings together Practice, Learn, Progress, Scoring, and Voice. The Chat CSE logo returns Home through the existing save/leave safeguards. Presentation illustrations and a saved evening theme support navigation; rehearsal keeps case titles and identifying illustrations sealed.

The written library has a dedicated **Print walkthrough** preview with landscape sheets throughout. The encounter uses numbered storyboard cards, actual simulation screenshots and credited public-domain equipment photographs. Later sections use two readable columns for reasoning, SOAP, evidence references, omissions and recall. Reused patient images are labeled representative, and variants retain their own authored dialogue and notes. Choose **Print / Save PDF** after reviewing the preview. Browser headers/footers are optional; the app includes its own page numbers. The solution-access check remains active before the preview and before printing.

The encounter now uses a single-screen workspace: Talk, Examine, Guide (assisted modes), and Record tabs keep the patient visible, with a persistent question entry and bedside/position/view/vitals/voice controls. Long records and explanations scroll within their panel. A labeled stacked layout preserves access on very small screens or high browser zoom. Cardiopulmonary illustrations use lungs; cardiovascular illustrations use a heart.

New Guided and Coached attempts have untimed encounters and notes, with no organization countdown. Independent practice gives 30 minutes for the encounter, 5 minutes to organize, and 20 minutes for SOAP. Exam rehearsal retains 14 minutes and 9 minutes without a practice break. Existing attempts preserve their original presets and deadlines.

Guided practice provides a case-specific next action, drafts questions without sending them, opens specific examination controls, and checks obtained evidence. Earlier unlocked cues can be revisited. Coverage checkpoints identify gaps; they are not certified rubric scores. Past Attempts includes per-case or all-progress reset with a preview, confirmation, and a separate unfinished-work acknowledgment.

The modern patient remains visible in all examination-sequence lessons. Standing and prone are recorded positioning choices in addition to seated/supine. Transfers use a brief fade, not a simulated physical transfer technique. Posture alone adds no examination findings. The SOAP grader's existing development limitations remain; this update does not establish overall study readiness.


A local-first CSE practice simulation with 24 presentations,48 additional variations and72 written walkthroughs. **Development preview: not clinically validated or study-ready.** The inherited SOAP checker can flag supported statements incorrectly and can give an incorrect repair exercise. Use the course rubric and supervising faculty to assess clinical accuracy; scores are provisional.

## Open the app

Public site: https://skempa7.github.io/pcm-cse-public/

Choose a mode and case, read the doorway/vitals, then enter. During the encounter, **Show anatomy view** reveals the unclothed clinical patient; **Show clothed view** returns. The female anatomical models use the same geometry, skin textures, rig and animation as the original local app. This is a visual option: changing views does not perform an examination or establish clinical findings. Patients start clothed and reload into the clothed view. Detailed vaginal/speculum and rectal inspection modules remain excluded. No arousal effects or sexualized clothing are included.

The public cohort contains 18 women and 6 men, all authored adults. The male patient is now generated directly from the adult male MPFB macro base, with a distinct male face, torso and proportions, bald head, light skin and light eyes. Male knitwear and trousers are fitted to that body; no female patient mesh or preserved female face is used. The avatar remains an illustrative clinical interface and is not a validated diagnostic anatomy model. This is a limited fictional practice cohort, not representative clinical or demographic coverage.

## Patient positions, examination lessons, and progress

**Adjust view** uses dragging to orbit around the patient, with **Zoom in** and **Zoom out** as the only movement buttons. Horizontal rotation covers a full 360 degrees; vertical rotation and zoom stay within patient/table and room limits. Face, Upper body, Full patient and Reset view restore useful framing. Ordinary wheel scrolling, browser zoom and touch/pinch gestures remain available.

The **Position** selector beneath the patient offers **Seated**, **Supine (face up)**, **Standing**, and **Prone (face down)**. The accepted position is saved in the encounter record and restored on reload. Authored refusals still apply. Changing position is simulated assistance and creates no examination findings. Face, Upper body, and Full patient adjust framing for the position. Standing/prone transfers use a brief visual fade; they are not demonstrations of hands-on transfer technique. Reduced motion goes directly to the same pose.

**Learn an examination sequence** uses the current detailed patient for all three lessons. A temporary teaching pose does not change the recorded encounter position. Closing the lesson restores that position and wardrobe. Older block-style patient roots are removed from the running scene, including comparison and fallback paths. Teaching markers are illustrative; hair can obscure posterior guides and they do not verify stethoscope contact or palpation force.

**Past attempts → Reset progress** can remove one presentation (all variations and retries) or the entire library. A preview counts all saved work, including older attempts; unfinished attempts require a separate opt-in. Confirmation permanently deletes the selected attempts, notes, scores, and written reflections. Voice, appearance, and other preferences remain. This release itself does not reset any progress.

**Scoring assumptions** now opens a points-first guide to the confirmed 100-point SOAP rubric, with specific requirements for Subjective 28, Objective 30, Assessment 15, Plan 25, and style 2. Separate encounter expectations follow; uncertain interpretations are last. This clarifies the rubric without correcting the inherited automated-grading defects.

Editable four-pose Blender scenes are delivered locally with repeatable `add_patient_postures.py` and `update_prone_support_profiles.py` steps. `web/patient3d/tests/positions.test.mjs` and `posture-support.test.mjs` import the actual GLBs to check poses and support. `tools/test_reset_ui.cjs` exercises reset safeguards; Python `tests/test_patient_positions.py` and `tests/test_progress_reset.py` use disposable databases. The retired female-to-male conversion is excluded from the exporter. Use `tools/build_mpfb_male.py` and `tools/add_male_postures.py` with the editable male source instructions to rebuild the native adult male and retain all four clips.

## No billable application services

The app has **no API key, paid AI module, hosted application server, payment integration, telemetry, Git LFS or custom paid build runner**. GitHub Pages serves static files. The Python encounter engine runs inside the visitor's browser using bundled Pyodide. Speech uses the browser/device default voice; optional speech recognition may use the browser vendor's service, with no app-owner credentials.

Visitors cannot spend the app creator's OpenAI balance through this build: that service and its credentials are absent. GitHub Pages for public repositories is available with GitHub Free and has usage limits; throttling or suspension can occur at those limits. No metered hosting fallback has been configured. Provider policies may change; this project does not enroll in paid services or auto-upgrade anything.

## Progress, timing and privacy

Work remains in IndexedDB/localStorage in the visitor's browser. There is no account or cross-device sync; clearing site data deletes local work. One active tab per origin prevents competing writes. GitHub receives normal static-page requests, but the app does not upload interviews, notes or scores to its creator.

Guided and Coached encounters and notes are untimed. Guided mode uses accelerated examination actions; Coached keeps the usual examination-action durations. Independent practice allows 30 minutes for the encounter, 5 minutes to organize, and 20 minutes for SOAP. Exam rehearsal alone uses the course 14-minute encounter and 9-minute SOAP with no organization interval. Existing saved attempts retain their original preset and deadlines. Reload retains absolute deadlines and saved work. Opening a walkthrough during an active independent/rehearsal attempt requires converting it to assisted practice. This is client-side practice software, not a secure/proctored exam platform.

## Run and edit locally

Use a current Chrome, Edge, Firefox or Safari browser. From this repository:

```
python3 -m http.server 8773 --bind 127.0.0.1
```

Open http://127.0.0.1:8773/web/. Do not open index.html directly from the filesystem; module workers and persistent browser storage need an HTTP(S) origin.

- `pcmcse/`, `offline_routes.py`: provider-free Python engine, authored case data and lessons.
- `web/engine-worker.mjs`, `web/public-runtime.js`: browser worker, persistent storage and local request adapter.
- `web/patient3d/src/`: Babylon.js integration. `package-lock.json` pins dependencies; run `npm ci` and `npm run build` in that folder to rebuild its bundle.
- Editable Blender 5.2.1 source scenes are delivered locally to the creator. Public glTF assets in `web/patient3d/assets/` can also be imported into Blender; no proprietary trial content is required.
- `tools/package_engine.py`: regenerate `web/engine.zip` after Python or case edits.
- `tools/build_teaching_library.py`: regenerate lessons using the actual encounter engine, against an isolated temporary database.
- `tools/validate_female_glb_parity.py`: compare the three female GLBs against the original export. Geometry, textures, rig, skinning and animation must match exactly; only wardrobe node names may differ.
- `tools/test_public_release.py`: run 72 route/workflow regression paths plus timing, locked notes, assistance gates and asset checks. These are structural tests, not medical validation.
- `tools/export_public_patients.py`: repeat the asset conversion with Blender 5.2.1 and `PCM_PRIVATE_ASSETS` pointing to a locally held original MPFB asset source and `PCM_PRIVATE_GLBS` to the original `web/patient3d/assets` directory. Female GLBs preserve the original binary payload exactly; only wardrobe node names change. The source scenes are never overwritten. Existing editable public scenes can be edited and re-exported without the private app or proprietary tools.

## Accuracy and limitations

Written walkthroughs are synthesized teaching examples tied to each case's evidence, not official station answers. The broader clinical-readiness review previously failed; public hosting does not change that result. Specific limitations include false unsupported-documentation flags, occasional scripted question misunderstandings, approximate mouth movement rather than accurate lip synchronization, basic model/cloth deformation, and limited anatomy. The system cannot assess palpation, tissue resistance, exact anatomical landmarks or hands-on technique.

Source-course files, the creator's saved attempts, private backend/credentials are not included. The existing licensed clinical character geometry is included for anatomical education. Source titles/locators document curriculum provenance without publishing private course PDFs, manuals or lecture files. This is independent student practice software, not an official institutional examination or medical-care tool.

Third-party licensing and source attribution: [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Application-specific code/content retains its existing author's rights; third-party assets retain their own licenses.
