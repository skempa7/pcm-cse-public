# Partner-practice printable cases — September 13, 2026

The printable edition now supports an in-person student/standardized-patient pair and individual study. It covers the existing 24 presentations and 72 resolved case paths. The encounter engine, canonical case facts, stored lessons, grading, timers, and saved student work are unchanged.

## Use

Open **Learn**, choose a presentation and case path, then **Print case documents**. Choose:

- **Patient role-play script** (the default): briefing and out-of-order history lookup, without examination results or the SOAP solution.
- **Simulated examination findings**: release rules, supplied information, and results tied to specific demonstrated actions.
- **Example SOAP answer key**: the defined example encounter and any limitations, followed by an ordinary portrait clinical note.
- **Complete study packet**: the patient script, examiner copy, demonstrated encounter, reasoning, revised-note references, recall, sources, and the SOAP key at the end.

The patient/examiner pages use Letter landscape; the SOAP key uses Letter portrait. The combined PDF contains both page orientations. The patient index and cross-references give physical page numbers; they also navigate within preview without changing the application route. Print each part separately to keep the solution out of sight.

## Patient script

The script distinguishes Ask, Say, focused follow-ups, and actor instructions using labels and typography as well as color. Broad questions have brief opening replies. Compound questions receive the requested parts immediately; actors do not withhold a reaction or dose that the question already requests. Bundled ROS replies are limited to the symptoms asked about. Missing facts are an out-of-role instruction, never an invented denial or a claim that the patient cannot remember.

All 2,827 authored facts are represented across the 72 paths. Canonical answer topics retain source fact identifiers internally; related sections use cross-references. Medication details supplied under HPI can be reached from Medications. Supported refusals and positioning behavior remain explicit. Demeanor is taken from actual acting directions; a concern stored in an affect field is not treated as a greeting.

The requested history order is **Surgical history; Medications; Allergies and reactions; Social history; History of present illness; Family history; Past medical history; Review of systems**. HPI remains directly accessible from the first-page index. ROS has system subheadings.

## Course terminology and evidence

The source review examined the PCM student manual/rubric/template, syllabus, CSE #1 announcement, orientation and communication materials, and the supplied acronym sheet. The acronym sheet says SMASH FMR without expanding it. The patient script therefore uses the user's requested category mapping without presenting that expansion as a verified course definition.

The clinical note follows the rubric's named Subjective sections: CC, paragraph HPI, PMH/PSH, medications, social history, family history, allergies and ROS. Objective distinguishes supplied information from performed examinations. Assessment is ranked; plans are paired and distinguish initial, conditional, and urgent parallel actions. Clinical teaching and authoring notices are outside the note.

The 14/9 versus 15/10 course timing discrepancy remains explicit. This print change does not alter application timing. The source's SP refusal rules remain in the examiner instructions.

The note describes the **complete demonstrated encounter**. It does not automatically import extra actor-reference facts. In particular, the positional-vertigo actor script includes a radiation response absent from the demonstrated encounter, and that fact is not added to its note. Source event links identify where to review the demonstrated evidence; they are not semantic proof of a paraphrase.

## Corrections and remaining authoring limits

The print adapter removes an unspoken sumatriptan dose, replaces an unprovided iron formulation with the supplied oral-iron history, and keeps observed pallor in Objective rather than describing it as patient-reported. The combined packet's revised-note evidence section uses the corrected note. The historical transcript remains identified as the recorded demonstration.

Maya's source dialogue uses both husband and boyfriend. The actor copy uses the unconflicting residence and one-male-partner information, with an explicit source-conflict instruction. The recorded transcript's conflict is labelled; it is not silently rewritten.

Six presentations (18 paths) lack support for the existing third differential: diarrhea/dehydration, right-upper abdominal pain, distal neuropathy, recurrent headache, acute urinary retention, and LUTS/nocturia. Their keys explicitly flag additional case authoring, omit the unsupported third entry from the clinical note, and retain it in internal audit metadata. They are not described as complete three-differential model answers. Review included the [ICHD-3 medication-overuse criteria](https://ichd-3.org/8-headache-attributed-to-a-substance-or-its-withdrawal/8-2-medication-overuse-headache-moh/) and [NIDDK's gastropathy causes](https://www.niddk.nih.gov/health-information/digestive-diseases/gastritis-gastropathy/symptoms-causes) for the specific exposure/frequency concerns.

Two additional presentations (6 paths) have course-plan limitations: palpitations lacks a clearly specified third MOTHERR element in one alternative plan; colicky flank pain lacks a specific routine follow-up interval and a clearly distinct third element in its third plan. These are flagged without inventing an interval or adding unnecessary care. Thus 24 paths have an authoring-gap notice, with different types of limitation.

The earlier lesson audit's 414 `not_evaluated` statements remain unresolved; this presentation pass does not relabel them as clinically validated. These are synthetic teaching examples, not faculty-approved answers.

## Verification and maintenance

The print adapters have focused all-path coverage tests and an independent six-case out-of-order lookup review. Corrections to the alias rules arose from actual lookup attempts and rendered-page review, not only field-count checks.

Reproducible entry points:

- `python3 -m unittest tests.test_partner_scripts tests.test_partner_notes`
- `node tools/test_print_walkthroughs.mjs` — preservation of the original chronological study source.
- `node tools/test_print_browser.cjs` — visible choices, default patient copy, page links, preserved reflection and reader position, cancellation, separate exports, narrow controls, failure/retry and protected solution access.
- `node tools/test_partner_print_layout.cjs` — isolated PDF layout checks for all four editions across 72 paths, using guarded runtime payloads and the served print modules. Set `PLAYWRIGHT_MODULE` and `CSE_TEST_OUTPUT` where required.
- `python3 tools/verify_partner_pdfs.py <output-directory>` — actual exported page counts, Letter geometry, text bounds, expected patient/note content, and matching source hashes. Requires PyMuPDF.

Layout fixtures do not establish visible-interface usability; browser workflow tests are separate. Text preservation does not establish clinical accuracy. Disposable attempts and temporary output directories are used throughout. QA PDFs and raster images are not published as static solution files.

## Completed release checks

- All 110 unit tests passed, including 22 actor-script checks and 10 note-adapter checks.
- All 72 teaching and public-route paths passed their existing integrity/access checks; 7,647 evidence-guarantee assertions passed. These remain separate from clinical validation.
- All four print editions were exported for every path: **288 PDFs, 3,078 pages**. Actual PDF counts matched pagination, all pages were Letter portrait or landscape as intended, and text stayed inside printable boundaries. The export audit verified 5,830 printed patient-response passages and 3,356 Subjective/Objective paragraphs, including their repeated appearance in the complete packets.
- Visible browser checks passed for the chooser, default patient copy, in-preview page links, separate SOAP/examiner PDF export, Return/Escape/cancel, nonzero scroll restoration, preserved reflection text, narrow controls, failed-image retry, slow access checks and solution-access failure. Actual visible-workflow SOAP and examiner exports matched their reported 4- and 2-page counts.
- Independent visual review covered 34 representative pages; 12 affected pages were rechecked against final PDF hashes after the alias, heading, cover and repeated-label corrections. The final two-page clinical note was also rendered and inspected directly.
- Nine locally served runtime/print assets matched the tested source bytes. Cache references, package contents, the provider-free boundary and publication inventory passed.

Patient copies span 6–9 landscape sheets; SOAP keys span 4–5 portrait sheets including the separate encounter-scope preface. Individual printer hardware and printer-driver scaling were not tested. PDF layout checks are not proof of accessibility compliance or faculty approval.
