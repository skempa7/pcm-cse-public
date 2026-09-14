# Chat CSE

A browser-local clinical-skills practice app: read the doorway information, interview and examine a simulated adult patient, write a SOAP note, and review feedback against the evidence you obtained.

**Public site:** https://skempa7.github.io/pcm-cse-public/web/

This public repository is the sole current application. The retired private server and standalone edition are not required. There are 34 fictional presentations, 82 case/variant paths, and 82 written walkthroughs. Clinical content and automated scoring remain provisional; this is independent student practice software, not a clinically validated assessment or an official institutional examination.

## Current experience

- **Talk:** type or dictate questions. Guided and Coached modes offer an encounter coach within Talk. Selected guidance stays available; Bedside suggestions become editable drafts with explicit choices when you already have writing. Stated actions are performed through the ordinary conversation path.
- **Physical Exam:** one-click actions perform the technique listed on each tile. Findings appear in the panel and are saved in **Notes**; its badge highlights new findings. Unavailable, declined, and interrupted actions do not become normal findings.
- **Notes:** a condensed summary of obtained information, with HPI organized by **OLDCARTS**. Missing information stays unknown. Choosing a view or opening a teaching suggestion creates no clinical evidence.
- **SOAP writing:** a full editor with permitted references alongside it on wide windows, or a writing/reference switch on narrower windows. Drafts, editing position, and recoverable writing are preserved; saving and submitting remain distinct.
- The top-left logo returns Home with save/leave safeguards. Progress contains saved attempts, original submissions, feedback and separate repairs/regrades.
- Patient camera controls are always available: drag to orbit, use the zoom icons and framing presets, or use the labeled View menu. The shirt icon switches clothing/anatomical appearance without performing an examination. Seated, supine, standing and prone are recorded position choices. Reduced motion retains the same final poses.
- Exam guide is a rehearsal aid. Its example documentation is conditional, not a finding obtained from clicking through the lesson. For printouts, use **Cases & print → choose a case → choose your materials**. Choose doorway information, patient script, examinations and findings, a blank SOAP workspace, example SOAP, student copy, or complete practice packet, then **Print / Save PDF**. Previews check solution access before showing or printing protected material. Patient scripts and examination findings use landscape pages; SOAP keys use portrait pages; complete packets combine both.

The current patient assets preserve the established bald male head with mustache, original female hair, body contours and clothing fit. Both shirts use AMERICA 250 artwork, on the male back and female front. The intentionally retained shirt/pants overlap can still show intersections. These models are illustrative surfaces, not validated diagnostic anatomy or hands-on examination simulators.

## Timing and evidence

| Mode | Encounter | Organization | SOAP |
| --- | --- | --- | --- |
| Guided | Untimed; shortened simulated exam durations | None | Untimed |
| Coached | Untimed; ordinary simulated exam durations | None | Untimed |
| Independent | 30 minutes | 5 minutes | 20 minutes |
| Exam rehearsal | 14 minutes | None | 9 minutes |

Saved attempts retain their original preset and absolute deadlines. Leaving a timed attempt does not pause it. Accessing solutions during an active independent/rehearsal attempt requires explicit conversion to assisted practice. Clinical credit derives from supplied or actually disclosed/examined evidence, not hidden case facts. Original submitted notes and grades remain frozen; **Recheck this note** evaluates the unchanged original with the current grader and saves a separate result. Editing through Deliberate practice remains a separate revision.

## Speech and privacy

There is no paid AI integration, owner API key, hosted application backend, telemetry, account or cross-device sync. GitHub Pages serves static files and Pyodide runs the Python engine locally in each visitor's browser. The application cannot spend the creator's OpenAI balance.

The fixed patient voices are **Google US English** for authored female patients and **Google UK English Male** for authored male patients. There is no voice selector or premium voice. If a required voice is unavailable, text still works and the app reports the limitation without substituting another voice. Voice on/off affects patient output only. In voice mode, click the microphone to start/stop hands-free listening; Escape cancels listening and patient speech. Browser speech recognition can use the browser vendor's network service and remains dependent on browser support and permission.

Attempts and recovery drafts live in IndexedDB/localStorage. Clearing site data removes them. Only one app tab may own the browser engine at a time. Failed storage writes block further mutations until the existing in-memory work can be saved; recovery does not repeat the original action. Keep the tab open and copy important text if a storage warning appears.

## Run and update

From this repository, start a local static server:

```sh
python3 -m http.server 8773 --bind 127.0.0.1
```

Open http://127.0.0.1:8773/web/. Opening HTML directly from the filesystem does not support module workers and browser storage correctly.

Current source and outputs:

- `pcmcse/` and `offline_routes.py`: current Python engine, authored cases, grading, teaching and local routes.
- `web/`: current interface and browser worker/storage adapter.
- `web/patient3d/src/`: current Babylon.js integration; `assets/` holds delivered runtime models and textures; `dist/room.js` is the compiled renderer.
- `pcmcse/teaching/lessons/`: generated written walkthroughs. Their engine/case stamps and replay checks must match current sources.
- `tools/` and `tests/`: verification and build tools. Original asset-generation/parity tools may require historical local inputs and are not a way to regenerate later manual artwork/body edits automatically.
- Ignored `editable-public-assets/`, `verification-private/` and `backups/`: local working material, not part of the published package. Do not publish these wholesale or replace runtime assets with an older export.
- Dated reports before September 12 describe historical snapshots, including retired private-edition checks; they are not current acceptance results. See `AUDIT-2026-09-12.md` for the independent review and `FRONTEND-PASS-2026-09-12.md` for the subsequent interface improvements and validation limits.

After Python, case or lesson edits run `python3 tools/package_engine.py`. For renderer edits, run `npm ci` and `npm run build` from `web/patient3d/`. Then run `python3 tools/stamp_cache_tags.py` once; it stamps the nested worker, iframe and print-module dependencies before the containing page. `--check` verifies freshness without changing files.

Verification entry points include `python3 -m unittest discover -s tests`, `python3 tools/test_public_release.py`, `python3 tools/test_evidence_guarantees.py`, `python3 tools/test_patient_chat.py`, and the focused tests described in the current audit. Browser integration checks require Playwright and a local static server. The tablet/visual regression set is `tools/test_case_selection.cjs`, `tools/test_ipad_workspace.cjs`, `tools/test_patient_rendering.cjs`, and `tools/test_patient_tablet.cjs`; use Chromium and WebKit where supported. These check case grouping and disclosure, touch workflows, actual patient geometry, loading recovery, and browser gesture ownership. Tablet emulation does not establish physical iPad performance, software-keyboard behavior, or microphone quality. `tools/test_print_browser.cjs` covers preview/export controls, title and reading-position restoration, print-style-load recovery, slow access checks, and protected printing. Use disposable databases and isolated browser profiles. Stage intended files before `python3 tools/build_manifest.py`; its `--check` verifies the public file inventory. Do not weaken evidence or publishing checks to obtain a pass.

## Boundaries and remaining limits

A broad test pass is not clinician validation of every fictional case, clinical explanation or free-text note. Missing authored history cannot safely become a fabricated denial. The symbolic dialogue/grader can still require clarification for unfamiliar wording. SOAP parsing accepts standalone, colon, dash and Markdown headings, repeated history sections, and multiline numbered assessment/plan entries. Clinical phrase matching remains bounded; feedback shows unverified passages and unresolved diagnosis mappings separately from established errors. Mouth movement, gestures and tissue/cloth behavior are approximate; no soft-tissue resistance, exact contact verification, or internal intimate examination is simulated.

Private course documents and real attempts are excluded. Source titles/locators preserve course provenance without publishing source materials. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and [the supplied-room notice](licenses/SUPPLIED-ROOM.md). The imported room's provenance/redistribution permission remains unverified; attribution is not a substitute for permission, and this application grants no new asset license.

### Partner practice printouts

**Cases & print** is the main document entry point. Choose a presentation and, where offered, its case path. Student materials (doorway, blank SOAP, combined student copy) contain no answers and do not change assistance status. Patient script, examination findings, example SOAP and full packet are clearly marked as answer materials and retain the independent/exam-rehearsal access gate.

The script uses first-person statements under HPI and spelled-out SMASH FMR history headings. Examination rows are grouped by system and are released only when performed/simulated. The blank SOAP provides two portrait writing pages. The example note uses only the complete demonstrated encounter; it is not permission to document hidden information in an individual attempt. Sources and the full online demonstration remain available under **Demonstration and sources**.

The September 14 expansion adds 10 distinct cardiovascular, respiratory, MSK, HEENT and skin presentations. See `PRINTABLE-CASES-2026-09-14.md` for inventory, review scope and remaining authoring limitations. The preceding `PARTNER-PRINT-2026-09-13.md` describes the superseded longer print format and its historical checks.
