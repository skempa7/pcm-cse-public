# Frontend and interaction pass — September 12, 2026

Status: frontend pass completed and verified locally; publication subsequently authorized by the user on September 12, 2026. The report below records that implementation pass. No paid service or private-edition recreation was added.

Open the running preview at http://127.0.0.1:8775/web/. Source: `/Users/sebastiankempa/pcm-cse-public`. The starting commit was `f4b70abd1735d2b96aabd83662b2ecff93def920`. This pass is a working-tree change to the public-only application. The retired private application was not modified or treated as a supported variant.

## Most consequential baseline problems

1. Drafting assistance could overwrite or compete with an unsent message. Selected guidance and examination-guide position could be lost on updates or reopening.
2. The patient pane retained too much space while examination actions and the patient summary were constrained; the conversation composer also occupied space when working elsewhere.
3. SOAP writing began below a large guidance block. Long text was clipped by the general composer height cap, and consulting information interrupted writing.
4. Examination actions, running state, and the destination of findings were not sufficiently connected. Bedside actions could show completion before success.
5. Setup and feedback made many secondary choices as prominent as the next useful action.

## Implemented changes

### Workspace and Talk

- Retained existing branding and one consolidated patient toolbar with direct supported positions, Bedside, View, Vitals, and a patient Voice toggle. Microphone input remains separate.
- Talk, Physical Exam, and Notes each receive appropriate room. The patient stays on the left; expanding the patient remains available.
- The composer stays in Talk, grows through comfortable multiline input, and retains Enter/Shift+Enter behavior. Other tasks provide a direct return to the saved draft.
- Reading position survives tab switches and new replies. Latest response returns to the current exchange without forcibly scrolling someone reading earlier messages.
- Pending requests block accidental duplicate submissions. Failed requests preserve recoverable text, including newer writing. Failed explicit Bedside actions can be retried immediately.
- Status distinguishes actual recording, processing, speaking, and idle presence. Typing a draft does not imply an active microphone.

### Assistance

- Bedside separates performing stated actions from preparing editable questions. Opening assistance alone records nothing.
- Shared drafting offers Add to my draft, Replace my draft, and Keep my draft when there is existing writing. Repeated insertion of the same suggestion is prevented. The selected suggestion remains available to revisit.
- The interview coach emphasizes one move and question, with rationale available on demand. Selected guidance remains pinned; Use next suggestion explicitly adopts a newer recommendation.
- Coach and guide position are stored per encounter. Closing, reopening, refreshing, or returning in another tab resumes the selected content. Another patient starts with separate state.
- Fixed the narrowly related coaching-stage bug: selecting a stage now produces that stage's move. No new evidence or grading credit is created by choosing it.
- The examination guide uses available space, provides readable diagrams and consistent navigation, and expands the patient pane on narrow windows while open. It preserves the distinction between rehearsal and examination of the current patient.

### Physical Exam and Notes

- Complaint-relevant core systems appear first; additional systems and the full catalog remain available. Search and selection survive task changes.
- Actions show selected, pending/running, completed, or unsuccessful states. Tile duration estimates reflect the existing simulation timing, including Guided mode; engine timing was not changed.
- Findings appear beside the action with Saved in Notes linking directly to the recorded examination section. Completion comes from the encounter ledger rather than an optimistic click marker.
- Notes presents compact information with visible OLDCARTS slots, readable wrapping, explicit Not yet recorded states, and optional original wording/source detail. Rendering does not authorize or invent additional facts.

### SOAP writing, setup, and feedback

- The note editor is immediately available; permitted guidance is optional. Student writing is never populated with suggested assessment or plan content.
- Wide windows use a readable editor and reference column. Narrow windows switch between writing and reference without discarding text, caret, selection, or scroll context.
- Reference options derive from the existing authorized payload. Rehearsal restrictions remain intact: only supplied chart information during the note, no encounter Notes/conversation/coaching, unchanged nine-minute note period.
- Textareas grow to long notes rather than clipping them. Save, retry, pending submission, cancellation, and submission errors preserve writing and give accurate feedback.
- Setup uses more compact mode and case selection without changing defaults or timers. Feedback emphasizes Priorities, Score, and Note comparison, with other named views retained under More feedback.
- End encounter, saving a draft, and Submit note remain distinct actions. Consequential confirmation is preserved.

## Arrangements compared

Using the same populated content at 1440×900, a wider work pane with the patient on the left was compared with the patient on the right. Keeping the patient on the left preserved the established spatial pattern while improving working width.

At 980px, an always-split SOAP layout offered approximately 618px of editor and 300px of reference. The selected transition layout provides approximately 938px for the current task. It adds one explicit transition at that width but preserves writing and place and avoids a narrow reference column.

## Validation and its limits

- Actual visible workflows used fresh disposable browser contexts. They included starting, populated interviewing, draft conflicts, Bedside drafting and recorded actions, direct examination and finding lookup, guides and backward navigation, note/reference use, saved-attempt resume, submission, and feedback.
- Interruption checks covered delayed replies while reading earlier messages, open guidance during updates, tab switches, existing/newer drafts, refresh, new-tab guide resume, save failures, failed submissions, and failed Bedside requests with immediate retry.
- Layout checks covered 1440×900, 1280×800, 820px, and 390px, plus 125% text enlargement. Native pointer/wheel interactions, keyboard targets and focus restoration were exercised. This is not a certification of accessibility compliance; native browser zoom and every assistive technology were not comprehensively tested.
- Long-note verification found baseline Subjective text clipped at 170px despite 333px of content. The corrected editor showed all content at 325/325px at 1440px and 350/350px at 1280px.
- Python regression suite: 77 tests passed. Public-route verification: 72 playable paths passed. These establish the tested behavior and route coverage, not universal clinical accuracy.
- Nine focused JavaScript suites passed: delayed speech, consolidated toolbar, 472 examination-sequence checks, hands-free speech, microphone lifecycle, reset, runtime recovery, voice policy, and worker persistence. Targeted assistance, guide-resume, and send-recovery browser scripts are also included in `tools/`.
- The Python change was packaged into `web/engine.zip`. Direct frontend assets were cache-stamped, and browser-loaded scripts/styles were compared with local bytes. The compiled 3D scene was not changed and did not require rebuilding.
- Microphone lifecycle and speech-failure behavior were tested with controlled browser substitutes. Actual microphone acoustics and voice availability on the user's device require the short hands-on trial. A missing prescribed device voice remains explicitly unavailable; no paid fallback was added.
- Conversation logic, grading substance, evidence policy, anatomy, and the full 3D scene were not independently re-audited in this frontend pass. The unresolved opening-statement/grading-evidence question remains separate and unchanged.

## Evidence and reproducibility

Local-only evidence is retained under `verification-private/frontend-20260912/`, which is already excluded from version control. It contains the paired screenshot gallery, populated screenshots, regression output, selected workflow reports, and a SHA-256 identity record for the final source. Browser fixtures belong only to disposable test attempts.

The gallery compares the original source with the final source using matching viewports, conversation prompts, draft text, and note text. The coach content can differ because the new version retains the selected move rather than silently adopting a background recommendation. Patient rendering, engine timing, and scoring remain governed by the existing implementation.

The temporary baseline preview served original changed files from the starting commit and unchanged assets from the current tree. An initially incorrect directory-index fallback was corrected before retaining the final comparisons. Missing assets in an early capture were detected through visual review; the local preview was restarted without console-output backpressure and retained screenshots required all styles and branding to load. Those earlier captures are not used as final evidence.

The public manifest is regenerated only for the intended tracked source inventory. Local screenshot fixtures and saved attempts are excluded. A manifest pass is an inventory/boundary check, not proof of usability.

## Changed implementation areas

- `web/app.js`: conversation state, request recovery, note workspace, lifecycle labels, and feedback organization.
- `web/encounter-workspace.js` / `.css`: task layout, shared drafting, Bedside, examination results, Notes, and guide integration.
- `web/learning.js`: retained guidance and shared draft entry points.
- `web/note-workspace.css` and `web/frontend-polish.css`: shared note, setup, and feedback presentation.
- `web/patient3d/technique.js` / `.css`: guide persistence, sizing, and diagram label presentation.
- `pcmcse/guide.py`: honoring the explicitly selected coaching stage.
- Engine package, cache references, and targeted regression scripts.

The existing toolbar test was updated because it required an optimistic recorded marker on click and a now-replaced inline drafting implementation. It now checks evidence-derived completion, explicitly rejects the premature marker, and retains position/voice/disclosure checks. No clinical or publishing assertion was weakened.
