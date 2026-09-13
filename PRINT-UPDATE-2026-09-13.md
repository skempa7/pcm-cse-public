# Printable walkthrough update — September 13, 2026

The public Learn library still contains 24 presentations and 72 case paths. This update refreshes its existing Letter-landscape print edition; it does not add a separate document generator or change encounter scoring, timing, student notes, or solution-access rules.

## Changes

- Five new screenshots captured from the current application, with image hashes, patient identity, posture, camera and capture provenance. Exact-patient captions require matching name, sex and age; other cases retain representative-image labels.
- Full vital-sign labels, shorter repeated image captions, fewer duplicate illustrations, and a compact explanation of Talk, Physical Exam, Notes, assistance, and note submission.
- Recall explanations begin on a new physical page after the recall prompts.
- Patient/presentation/path-specific PDF titles, restored reader focus and scroll position, and reachable preview controls at a 390px viewport.
- Versioned image URLs and recursive cache stamping for print CSS and the image manifest. Print changes now invalidate their containing module and page in one pass.
- A background access-status probe no longer cancels the verification initiated by a Print click. Access changes and failed verification still hide the solution and revoke printing permission.
- Corrected one existing teaching overstatement in the epigastric-pain case: medication exposure informs assessment but does not establish a diagnosis. Also normalized “stool color” to US English. The canonical case and its three generated lessons agree. The distinction is supported by [NIDDK’s diagnostic overview](https://www.niddk.nih.gov/health-information/digestive-diseases/peptic-ulcers-stomach-ulcers/diagnosis). Dialogue, examination findings, SOAP content and evidence links were preserved.

## Verification

- All 72 lessons replayed against the engine; initially, all matched the existing generated lessons. After the wording correction, only the three affected lessons were regenerated and their dialogue, findings, notes and evidence were compared with the prior version.
- The print structural check preserves 4,027 chronological turns and 4,427 note links across all 72 paths.
- Chrome rendered all 72 PDF documents. There were no overflowing columns, oversized blocks, missing images, incorrect case/path assignments, or page JavaScript errors. PDF page counts matched the browser pagination report, and all pages were Letter landscape.
- PDF text extraction verified all 13,183 checked dialogue, action, finding, explanation, note and recall passages. This tests preservation, not clinical accuracy.
- Visual inspection covered 13 representative rasterized pages, including openings, current male/female images, urgent and variant paths, the new workflow block, SOAP, evidence, recall, answers and sources. Affected pages were inspected again after the wording correction.
- The focused browser test exercises Return, Escape, document titles, nonzero reader-scroll restoration, narrow preview controls, the native-print event lifecycle, failed image-manifest loading and retry, a slow access request overlapping periodic checks, and access failure under print media.
- All 78 Python regression tests passed. The four cache-chain tests and provider-free check passed; cache references were current. Publication checks are recorded with the release. QA PDFs, images, scripts and reports remain local under ignored `verification-private/print-20260913/`.

## Practical limits

The clinical library is source-linked teaching material, not a faculty-approved answer key. Its existing `not_evaluated` audit statements remain explicit. This pass verifies printable preservation and usability and corrects the specific overstatement above; it is not a new clinical review of every teaching statement. Native paper-printer hardware was not tested. The landscape paper preview retains its physical width on narrow screens while its controls reflow.

## Use

Open the public app → Learn → choose a presentation and case path → Print walkthrough → Print / Save PDF.
