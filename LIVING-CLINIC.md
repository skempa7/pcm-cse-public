# Patient motion and combined room update

The patient now uses position-aware arm and hand gestures for disclosed abdominal, chest, head, flank/back, shoulder, and knee complaints. Facial discomfort blends with existing blinking and speech movement. The animation system uses the existing skeleton and procedural inverse kinematics, not imported motion capture. Mouth motion remains approximate.

Gestures illustrate reported locations; they never establish tenderness or add examination evidence. Hidden case findings are not consulted by the new gesture selector. Reduced motion disables gestures. Prone anterior complaints use restrained supported-hand movement rather than reaching through the table. Standing knee reaching is omitted until a safe full-body bend is authored.

The room combines user-supplied InteriorTest geometry with the earlier folder's wood textures. Static lighting is baked for browser rendering. The movable examination table remains dynamic. The wall flag is original geometry. See licenses/SUPPLIED-ROOM.md for provenance and limitations.

## Verification scope
- 24-case gesture disclosure checks: no ledger mutation, no hidden-finding dependence, and correct handling of uncertain replies.
- 72 public case/variant route regressions, including submission locks and disabled billing routes. These are structural software checks, not comprehensive clinical review.
- Direct Chrome motion checks across nine profile/complaint/posture combinations, including women and men, three female body builds, and seated, supine, prone, and standing.
- Disposable browser encounter: examination feedback, new-Record badge, reload recovery, reduced motion, organization-to-note transition, and SOAP submission.
- No paid API requests were made. No case data or existing saved attempts were migrated or reset.

This is not an independent readiness certification. Existing grading limitations and the development-preview status remain. Gestures are approximate; residual clothing overlap and some pose-contact limitations remain. No claim of photorealism or accurate lip synchronization is made.

The browser debrief check exposed a pre-existing division-by-zero error in coached untimed attempts with an examination. Time feedback now uses the actual untimed policy and displays elapsed time without a percentage or deadline. Coached, guided, independent, and rehearsal timing-feedback regressions were added.
