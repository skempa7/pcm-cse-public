# Examination demonstrations — September 15, 2026

## What changed

Every one of the 85 selectable examination actions has a neutral technique demonstration. These are original procedural SVG diagrams, not recordings of the simulated patient's findings. Each sequence names the setup, shows its specific body site and method, and ends at the engine's completion time. Observation stages deliberately remain still. The original patient scene, available examination findings, scoring and disclosure rules are preserved.

The small **Skip animation** control completes an eligible examination and advances a timed encounter by its exact unwatched milliseconds. Natural completion does not charge again. Untimed modes have no skip penalty. **Cancel examination** interrupts the action without a finding; **Replay technique** is teaching only. Starting, skipping, cancellation and stale/repeated controls are tied to one examination identifier. Position controls and other examinations remain unavailable during a pending examination.

## Timing decisions

The catalog is `pcmcse/exam_demonstrations.json`; its stage durations sum to the action duration. The tile, Python pending interval, animation and progress all consume that same plan. Python owns finding release. There is no client-only completion path.

- JVD remains 15 seconds: setup/venous observation/reference measurement.
- Heart auscultation now has four 10-second listening sites (40 seconds).
- Lung auscultation compares 14 sites in 58 seconds, retaining anterior, three posterior levels and lateral coverage with one breath at each site.
- Orthostatic measurements include 300 seconds supine rest, 10 seconds baseline measurement, 5 seconds assisted standing, and measurements at 1 and 3 minutes standing: 495 seconds total. The former assumption that rest happened before the action is removed. These are simulation intervals; real cuff measurements may require more time.
- Dix–Hallpike side actions include suitability screening, head positioning, assisted reclining, 30 seconds observation, return and recovery: 79 seconds. The separate 16-second suitability screen remains available.
- Mental status includes a two-minute delay between registration and recall (152 seconds total); immediate repetition alone is not presented as delayed memory testing.
- Guided mode no longer compresses demonstrations to 15% speed. It is still untimed and can skip without a countdown penalty.
- Existing pending examinations keep their original due time after update; the renderer fits the current neutral plan to that saved interval. Original submitted attempts are not rewritten.

The written walkthrough now projects its estimate using current examination durations while preserving its original evidence ledger. Nine existing case paths exceed 14 minutes with these fuller demonstrations (thunderclap headache, flank pain and presyncope variants); the reader identifies them as full untimed study walkthroughs instead of displaying the obsolete shorter estimate. A timed student encounter still requires a focused choice of examinations.

No overall mode budget, grading criterion, clinical case fact or examination-result mapping was changed. Counts and timings below are simulation design decisions, not claims about the exact time required in a real patient.

## Course reference and technique sources

Primary course materials were read locally, without adding private PDFs to the public package:

- *Principles of Clinical Medicine I & II — Student Manual*, revised June 2026, Fall 2026/Winter 2027. Page 10 specifies bilateral anterior/posterior/lateral lung listening with three posterior levels, open-mouth breathing and skin contact; 4–6 heart listening posts; and the ear, nose, throat, skin, sinus and cervical-node methods. Page 21 reinforces side-to-side levels, abdominal order, draping and position help.
- *PCM I Announcement CSE #1 Fall 2026 updated*, pages 1–3: area-of-concern priority, direct skin contact, station restrictions and documentation of obtained findings. Its conflicting timing statements were not used to change established app budgets.
- *PCM Lab 1 SOAP Note* and the PCM syllabus support documentation/context, not a comprehensive technique manual.

The course documents do not provide detailed technique for all 85 actions. Supplementary references below informed the original diagrams and concise captions. Links identify the source families stored in each plan's `sources`; there is no claim of institutional endorsement, licensed video reproduction or faculty review.

| Source keys | Reference and use |
| --- | --- |
| course | Local course titles/pages above; station scope, methods, sequencing and evidence boundaries |
| clinicalmethods, heent, neck | [Clinical Methods — The Physical Examination](https://www.ncbi.nlm.nih.gov/books/NBK361/?report=printable); [Head and Neck](https://www.ncbi.nlm.nih.gov/books/NBK223/): regional inspection/palpation and screening methods |
| vascular | [Clinical Methods extremity pulses and bruits](https://www.ncbi.nlm.nih.gov/books/NBK350/?report=printable): pulse sites and vascular examination |
| skin | [Merck dermatologic examination](https://www.merckmanuals.com/professional/dermatologic-disorders/approach-to-the-dermatologic-patient/evaluation-of-the-dermatologic-patient): inspection and lesion palpation |
| renal | [Merck urologic examination](https://www.merckmanuals.com/professional/genitourinary-disorders/approach-to-the-patient-with-urologic-issues/evaluation-of-the-patient-with-urologic-issues): costovertebral angle and blunt percussion |
| heart, precordium | [Stanford cardiac examination](https://med.stanford.edu/stanfordmedicine25/the25/cardiac.html), [precordial movements](https://stanfordmedicine25.stanford.edu/the25/precordial.html): listening landmarks, inspection and palpation |
| jvp | [Stanford JVP measurement](https://med.stanford.edu/stanfordmedicine25/the25/neck-exam-jugular-venous-pressure-measurement.html): recline, venous observation and sternal reference |
| pulmonary | [Stanford pulmonary examination](https://med.stanford.edu/stanfordmedicine25/the25/pulmonary.html): comparison sites, percussion, fremitus and chest observation |
| abdomen | [Clinical Methods abdominal examination](https://www.ncbi.nlm.nih.gov/books/NBK420/?report=reader), [acute abdominal examination](https://pmc.ncbi.nlm.nih.gov/articles/PMC3468117/): inspection/listening/palpation/percussion and selected special tests |
| liver, ascites | [Stanford liver examination](https://med.stanford.edu/stanfordmedicine25/the25/liver.html), [ascites examination](https://med.stanford.edu/stanfordmedicine25/the25/avp.html): liver borders and shifting-dullness sequence |
| lymph, thyroid | [Stanford lymph nodes](https://med.stanford.edu/stanfordmedicine25/the25/lymph.html), [thyroid](https://med.stanford.edu/stanfordmedicine25/the25/thyroid.html): palpation groups, landmarks and swallowing |
| ear, fundus, pupils | [Clinical Methods ears](https://www.ncbi.nlm.nih.gov/books/NBK231/), [Stanford fundoscopic examination](https://med.stanford.edu/stanfordmedicine25/the25/fundoscopic.html), cranial reference below: equipment approach and visual testing |
| cranial | [Merck cranial nerves](https://www.merckmanuals.com/professional/neurologic-disorders/neurologic-examination/how-to-assess-the-cranial-nerves): sensory territories, eye targets, facial/jaw/tongue movement and resistance |
| motor, sensory, reflexes | [Merck motor assessment](https://www.merckmanuals.com/professional/neurologic-disorders/neurologic-examination/how-to-assess-the-motor-system), [sensation](https://www.merckmanuals.com/professional/neurologic-disorders/neurologic-examination/how-to-assess-sensation), [reflexes](https://www.merckmanuals.com/professional/neurologic-disorders/neurologic-examination/how-to-assess-reflexes): stabilization, comparison, instruments and tendon sites |
| coordination, gait | [Stanford cerebellar examination](https://med.stanford.edu/stanfordmedicine25/the25/cerebellar.html): finger–nose, alternating movement, heel–shin, guarded balance and gait observation; Romberg is a proprioception/balance test, not a specific cerebellar sign |
| mental | [Merck mental status](https://www.merckmanuals.com/professional/neurologic-disorders/neurologic-examination/how-to-assess-mental-status): observed behavior, orientation, attention and memory prompts |
| msk, back | [Stanford shoulder](https://med.stanford.edu/stanfordmedicine25/the25/shoulder.html), [knee](https://med.stanford.edu/stanfordmedicine25/the25/knee.html), [low back](https://stanfordmedicine25.stanford.edu/the25/BackExam.html): active regional motion and straight-leg testing |
| meningeal | [Merck meningeal signs](https://www.merckmanuals.com/professional/neurologic-disorders/meningitis/overview-of-meningitis?media=full): supported passive neck/leg movement; avoid force and stop if unsafe |
| orthostatic | [CDC orthostatic BP procedure](https://www.cdc.gov/steadi/media/pdfs/STEADI-Assessment-MeasuringBP-508.pdf): five-minute rest and 1-/3-minute standing measurements |
| dix | [AAO-HNS BPPV guidance](https://www.entnet.org/quality-practice/quality-products/clinical-practice-guidelines/bppv/): suitability, 45-degree head turn and approximately 20-degree head extension; this more specific procedure is used where general summaries differ |
| osteopathic | [Osteopathic palpation review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9491508/): regional tissue texture, asymmetry, restriction and tenderness; gentle screening only, no treatment thrusts |

## Coverage inventory

Each row below is one selectable action, including alternative positions, regions and individual nerve/sensory/reflex choices. The separate supplied-vitals review has a neutral chart diagram but is not counted as a performed physical examination. Existing refusal proposals for intimate examinations remain refusal workflows, not performed maneuvers.

| Action | Simulation seconds | Stages | Source keys |
| --- | ---: | ---: | --- |
| General appearance (`general_inspect:complete`) | 10 | 2 | course, clinicalmethods |
| Inspect pupils, conjunctivae, sclerae and corneas (`heent_eyes:inspect`) | 19 | 3 | course, pupils |
| Check extraocular movements (`heent_eyes:eye-movement`) | 12 | 1 | course, cranial |
| Perform fundoscopic examination (`heent_eyes:fundus`) | 20 | 3 | course, fundus |
| Otoscopic exam of ears (`heent_ears:complete`) | 16 | 2 | course, ear |
| Inspect nose with light source (`heent_nose:complete`) | 15 | 2 | course, heent |
| Inspect mouth and throat with light (`heent_throat:complete`) | 18 | 3 | course, cranial |
| Palpate / percuss sinuses (`heent_sinuses:complete`) | 12 | 2 | course, heent |
| Palpate lymph nodes (`lymph_nodes:complete`) | 24 | 3 | course, lymph |
| Palpate thyroid (`thyroid:complete`) | 19 | 3 | course, thyroid |
| Check neck flexion and rotation (`neck_rom:rom`) | 14 | 2 | course, neck |
| Perform Brudzinski test (`neck_rom:brudzinski`) | 12 | 2 | course, meningeal |
| Perform Kernig test (`neck_rom:kernig`) | 19 | 3 | course, meningeal |
| Listen at all four heart valve areas, on skin (`heart_auscultate:all`) | 40 | 4 | course, heart |
| Inspect / palpate precordium, PMI (`heart_inspect_palpate:complete`) | 23 | 4 | course, precordium |
| Assess jugular venous distention (`jvd:complete`) | 15 | 3 | course, jvp |
| Palpate peripheral pulses (`peripheral_pulses:complete`) | 28 | 4 | course, vascular |
| Auscultate carotid arteries (`carotid_auscultate:complete`) | 16 | 2 | course, vascular |
| Listen to lungs — compare both sides, front, back and sides (`lungs_auscultate:all`) | 58 | 14 | course, pulmonary |
| Percuss lung fields (`lungs_percuss:complete`) | 36 | 2 | course, pulmonary |
| Assess tactile fremitus (`lungs_fremitus:complete`) | 18 | 1 | course, pulmonary |
| Inspect chest wall (`chest_inspect:complete`) | 15 | 2 | course, pulmonary |
| Palpate chest wall (`chest_wall_palpate:complete`) | 18 | 2 | course, pulmonary |
| Inspect abdomen (`abd_inspect:complete`) | 12 | 2 | course, abdomen |
| Listen for bowel sounds in all four quadrants (`abd_auscultate:sounds`) | 28 | 5 | course, abdomen |
| Listen for abdominal bruits (`abd_auscultate:bruits`) | 25 | 5 | course, abdomen |
| Percuss all four abdominal quadrants (`abd_percuss:quadrants`) | 16 | 1 | course, abdomen |
| Percuss liver span (`abd_percuss:liver`) | 21 | 3 | course, liver |
| Check shifting dullness (`abd_percuss:ascites`) | 27 | 4 | course, ascites |
| Lightly palpate all quadrants; assess guarding (`abd_palpate:light`) | 20 | 2 | course, abdomen |
| Deeply palpate all four quadrants (`abd_palpate:deep`) | 20 | 1 | course, abdomen |
| Assess rebound tenderness (`abd_palpate:rebound`) | 10 | 2 | course, abdomen |
| Perform Murphy sign (`abd_special:0`) | 13 | 2 | course, abdomen |
| Assess McBurney-point tenderness (`abd_special:1`) | 12 | 2 | course, abdomen |
| Perform Rovsing sign (`abd_special:2`) | 12 | 2 | course, abdomen |
| Perform psoas test (`abd_special:3`) | 12 | 2 | course, abdomen |
| Perform obturator test (`abd_special:4`) | 12 | 2 | course, abdomen |
| Check costovertebral-angle tenderness (`abd_special:5`) | 12 | 2 | course, renal |
| Inspect the affected area (`msk_inspect:complete`) | 12 | 1 | course, msk |
| Palpate the affected area — point tenderness (`msk_palpate:0`) | 12 | 1 | course, msk |
| Palpate the affected area — paraspinal musculature (`msk_palpate:1`) | 18 | 1 | course, back |
| Palpate the affected area — midline spine (`msk_palpate:2`) | 15 | 1 | course, back |
| Range of motion (`msk_rom:complete`) | 28 | 4 | course, msk |
| Muscle strength testing — upper extremity (`msk_strength:0`) | 32 | 5 | course, motor |
| Muscle strength testing — lower extremity (`msk_strength:1`) | 20 | 3 | course, motor |
| Muscle strength testing — pronator drift (`msk_strength:2`) | 24 | 2 | course, motor |
| Supine straight-leg raise — both legs (`msk_slr:supine`) | 20 | 2 | course, back |
| Seated straight-leg raise — both legs (`msk_slr:seated`) | 20 | 2 | course, back |
| Observe gait (`gait:complete`) | 16 | 2 | course, gait |
| Cranial nerve examination — cn ii (`neuro_cn:0`) | 30 | 3 | course, cranial |
| Cranial nerve examination — cn iii-iv-vi (`neuro_cn:1`) | 20 | 2 | course, cranial |
| Cranial nerve examination — cn v (`neuro_cn:2`) | 23 | 3 | course, cranial |
| Cranial nerve examination — cn vii (`neuro_cn:3`) | 19 | 4 | course, cranial |
| Cranial nerve examination — cn viii (`neuro_cn:4`) | 14 | 2 | course, cranial |
| Cranial nerve examination — cn ix-x (`neuro_cn:5`) | 13 | 2 | course, cranial |
| Cranial nerve examination — cn xi (`neuro_cn:6`) | 15 | 2 | course, cranial |
| Cranial nerve examination — cn xii (`neuro_cn:7`) | 19 | 3 | course, cranial |
| Sensory examination — light touch (`neuro_sensory:0`) | 16 | 1 | course, sensory |
| Sensory examination — pinprick (`neuro_sensory:1`) | 16 | 1 | course, sensory |
| Sensory examination — vibration (`neuro_sensory:2`) | 14 | 2 | course, sensory |
| Sensory examination — proprioception (`neuro_sensory:3`) | 13 | 2 | course, sensory |
| Check biceps, triceps, patellar and Achilles reflexes (`neuro_reflexes:dtr`) | 32 | 8 | course, reflexes |
| Check plantar response (Babinski) (`neuro_reflexes:plantar`) | 16 | 2 | course, reflexes |
| Coordination / cerebellar — finger to nose (`neuro_coordination:0`) | 14 | 1 | course, coordination |
| Coordination / cerebellar — heel to shin (`neuro_coordination:1`) | 16 | 2 | course, coordination |
| Coordination / cerebellar — romberg (`neuro_coordination:2`) | 28 | 2 | course, coordination |
| Coordination / cerebellar — rapid alternating (`neuro_coordination:3`) | 12 | 1 | course, coordination |
| Mental status / orientation (`mental_status:complete`) | 152 | 5 | course, mental |
| Inspect skin — chest (`skin_inspect:0`) | 10 | 1 | course, skin |
| Inspect skin — back (`skin_inspect:1`) | 10 | 1 | course, skin |
| Inspect skin — arms (`skin_inspect:2`) | 10 | 1 | course, skin |
| Inspect skin — legs (`skin_inspect:3`) | 10 | 1 | course, skin |
| Inspect skin — palms (`skin_inspect:4`) | 10 | 1 | course, skin |
| Inspect skin — soles (`skin_inspect:5`) | 10 | 1 | course, skin |
| Palpate the skin concern (`skin_palpate:complete`) | 16 | 3 | course, skin |
| Inspect / palpate extremities (`extremities:complete`) | 32 | 5 | course, vascular |
| Osteopathic structural screen — cervical (`osteo_screen:0`) | 16 | 2 | course, osteopathic |
| Osteopathic structural screen — thoracic (`osteo_screen:1`) | 16 | 2 | course, osteopathic |
| Osteopathic structural screen — lumbar (`osteo_screen:2`) | 16 | 2 | course, osteopathic |
| Osteopathic structural screen — sacrum (`osteo_screen:3`) | 16 | 2 | course, osteopathic |
| Osteopathic structural screen — ribs (`osteo_screen:4`) | 16 | 2 | course, osteopathic |
| Orthostatic vital signs (`orthostatic_vitals:complete`) | 495 | 5 | course, orthostatic |
| Check cervical and positional-test suitability first (`neuro_dix_hallpike:screen`) | 16 | 2 | course, dix |
| Dix–Hallpike, right — includes suitability check (`neuro_dix_hallpike:right`) | 79 | 7 | course, dix |
| Dix–Hallpike, left — includes suitability check (`neuro_dix_hallpike:left`) | 79 | 7 | course, dix |

## Reproducible verification

- `python3 -m unittest tests.test_exam_animation_lifecycle -v`: all 85 mappings and natural completions, stable legacy identifiers, partial coach selections, exact skip milliseconds, duplicate/stale controls, cancellation, untimed modes and deadline behavior.
- `tools/test_exam_animation_catalog.cjs`: selects each actual tile in a fresh disposable browser attempt, checks the displayed/pending duration, skips via the visible control, and checks completed status and preserved draft. Produces results and per-action visual review sheets.
- `tools/test_exam_animation_controls.cjs`: watches JVD at real speed; performs partial/repeated skips, replay, cancellation, injected control failure/retry, refresh/resume, desktop/tablet reflow and a deadline crossing through visible controls. Confirms served source/build hashes.
- `tools/test_exam_animation_regions.cjs`: watches hand, shoulder and knee range-of-motion actions through all four stages and natural completion in their actual cases.
- `tools/test_exam_animation_motion.cjs`: plays each authored stage at its actual speed, records successive rendered frames and captures timestamped contact sheets. Static long waits are sampled; their complete duration is checked by the engine lifecycle tests. Motion/geometry checks do not establish clinical accuracy by themselves.

Browser checks accept `PLAYWRIGHT_MODULE`, `CSE_TEST_URL` and `CSE_TEST_OUTPUT`. Use a fresh browser context; these checks create disposable attempts and never edit personal saved encounters.

## Practical limits

These are explanatory two-dimensional technique models. The mint hands represent examiner contact; they do not measure real force, angle, diagnostic skill or hands-on proficiency. The diagrams never animate an unobserved patient-specific abnormality. Findings must be read from the completed action/Notes, not inferred from the neutral drawing. Regional MSK motion uses the publicly selected complaint region; generic actions show a representative site and preserve the case's existing evidence semantics.

Course technique videos were not available for this pass. Clinical source review and software tests are not a faculty/clinician validation of all demonstrations. Tablet viewport checks do not establish physical iPad, software keyboard or microphone performance. The change is local until explicitly released; prior production screenshots are not proof of this build.
