/* Minimum effective physical examination sequences for a student CSE.
 *
 * DESIGN INTENT
 * These are deliberately SHORT. The goal is the smallest sequence a student can
 * perform quickly and reliably under time pressure that still supports an
 * honest physical-examination paragraph in a SOAP note. Comprehensive
 * textbook examinations are explicitly out of scope: anything slow, hard to
 * remember, highly condition-specific, or unlikely to change the note is left
 * out of the core sequence and listed under `optional` instead.
 *
 * DOCUMENTATION DISCIPLINE
 * Every step carries its own `soap` fragment. The closing summary is assembled
 * ONLY from the steps actually completed, so the sequence can never teach a
 * student to document a component they did not perform. A step with no `soap`
 * contributes nothing to the note.
 *
 * This file is DATA. Adding a step, changing wording, or adding a whole new
 * system is an edit here and nowhere else.
 */
(() => {
  // Demonstration specs are interpreted by the diagram renderer in
  // technique.js. `view` selects the body schematic; `marks` are the numbered
  // or paired locations; `arrows` show direction of progression.
  const EXAMS = {
    cardiac: {
      id: 'cardiac',
      title: 'Cardiac',
      blurb: 'Inspection, pulse, precordium, four auscultation areas.',
      duration: '~60 seconds',
      position: 'Patient seated or at 30–45°. Chest exposed as needed, draped.',
      steps: [
        {
          id: 'inspect',
          title: 'Inspect',
          instruction: 'Look at the patient and the precordium. Note comfort at rest, work of breathing, color, and any visible chest wall pulsation.',
          assessing: 'Distress, cyanosis, visible heave or lift.',
          normal: 'Comfortable at rest, no cyanosis, no visible precordial impulse.',
          soap: 'Comfortable at rest',
          demo: { view: 'torso-front', caption: 'Look before you touch', marks: [{ x: 50, y: 40, r: 26, kind: 'zone', label: 'precordium' }] },
        },
        {
          id: 'pulse',
          title: 'Palpate the radial pulse',
          instruction: 'Two fingers on the radial artery. Count for about 15 seconds and feel whether the rhythm is regular.',
          assessing: 'Rate and rhythm.',
          normal: 'Rate 60–100, regular.',
          soap: 'rate and rhythm regular',
          demo: { view: 'arm', caption: 'Two fingers, radial artery', marks: [{ x: 72, y: 62, r: 7, kind: 'hand', label: 'radial' }] },
        },
        {
          id: 'pmi',
          title: 'Palpate the precordium',
          instruction: 'Fingerpads at the 5th intercostal space, midclavicular line, to feel the apical impulse. A quick check — do not hunt for it.',
          assessing: 'Apical impulse location; any thrill or heave.',
          normal: 'PMI non-displaced, no thrills or heaves.',
          soap: 'PMI non-displaced, no thrills or heaves',
          demo: { view: 'torso-front', caption: 'Apex: 5th ICS, midclavicular line (patient\'s left)', marks: [{ x: 65, y: 61, r: 8, kind: 'hand', label: 'PMI' }] },
        },
        {
          id: 'auscultate',
          title: 'Auscultate four areas',
          instruction: 'Diaphragm on skin. Aortic → pulmonic → tricuspid → mitral. A few seconds at each.',
          assessing: 'S1 and S2, extra sounds, murmurs, rubs, gallops.',
          normal: 'S1 and S2 normal, no murmurs, rubs, or gallops.',
          soap: 'normal S1/S2, no murmurs, rubs, or gallops',
          demo: {
            view: 'torso-front', caption: 'Aortic → pulmonic → tricuspid → mitral',
            // Front view: the patient's right side is on the viewer's LEFT.
            marks: [
              { x: 41, y: 30, r: 6.5, kind: 'scope', label: '1', title: 'Aortic — right 2nd intercostal space' },
              { x: 59, y: 30, r: 6.5, kind: 'scope', label: '2', title: 'Pulmonic — left 2nd intercostal space' },
              { x: 56, y: 49, r: 6.5, kind: 'scope', label: '3', title: 'Tricuspid — left lower sternal border' },
              { x: 65, y: 61, r: 6.5, kind: 'scope', label: '4', title: 'Mitral — apex, 5th ICS midclavicular' },
            ],
            arrows: [[0, 1], [1, 2], [2, 3]],
          },
        },
      ],
      optional: [
        { title: 'Carotid auscultation', why: 'Adds a bruit check; useful with a murmur or vascular risk.' },
        { title: 'Bell at the apex', why: 'For a low-pitched S3/S4 or mitral stenosis murmur.' },
        { title: 'JVP assessment', why: 'Slow and hard to do reliably; reserve for suspected heart failure.' },
        { title: 'Peripheral edema', why: 'Quick and worth adding when volume overload is a question.' },
      ],
      soapPrefix: 'CV:',
    },

    pulmonary: {
      id: 'pulmonary',
      title: 'Pulmonary',
      blurb: 'Effort, expansion, systematic bilateral auscultation.',
      duration: '~45–60 seconds',
      position: 'Patient seated, leaning slightly forward for the posterior fields. Listen on skin.',
      steps: [
        {
          id: 'inspect',
          title: 'Inspect',
          instruction: 'Watch a few breaths from the end of the bed. Note rate, effort, accessory muscle use, and whether the chest moves symmetrically.',
          assessing: 'Respiratory effort and chest symmetry.',
          normal: 'Unlaboured breathing, symmetric chest movement, no accessory muscle use.',
          soap: 'normal respiratory effort',
          demo: { view: 'torso-front', caption: 'Watch a few quiet breaths', marks: [{ x: 50, y: 45, r: 30, kind: 'zone', label: 'chest' }] },
        },
        {
          id: 'expansion',
          title: 'Assess chest expansion',
          instruction: 'Thumbs at the level of the 10th ribs posteriorly, hands wrapping the flanks. Ask for a deep breath and watch your thumbs move apart.',
          assessing: 'Symmetry of expansion.',
          normal: 'Symmetric chest expansion.',
          soap: 'symmetric chest expansion',
          demo: {
            view: 'torso-back', caption: 'Thumbs together, watch them separate',
            marks: [{ x: 44, y: 62, r: 7, kind: 'hand' }, { x: 56, y: 62, r: 7, kind: 'hand' }],
            arrows: [[0, 1, 'apart']],
          },
        },
        {
          id: 'auscultate',
          title: 'Auscultate posteriorly',
          instruction: 'Diaphragm on skin, patient breathing through an open mouth. Upper, middle, then lower — comparing left and right at each level before moving down.',
          assessing: 'Breath sounds side to side; wheezes, crackles, or decreased sounds.',
          normal: 'Clear to auscultation bilaterally, no wheezes, crackles, or rhonchi.',
          soap: 'clear to auscultation bilaterally without wheezes, crackles, or rhonchi',
          demo: {
            view: 'torso-back', caption: 'Compare left ↔ right at each level',
            marks: [
              { x: 42, y: 34, r: 7, kind: 'scope', label: '1' }, { x: 58, y: 34, r: 7, kind: 'scope', label: '2' },
              { x: 42, y: 50, r: 7, kind: 'scope', label: '3' }, { x: 58, y: 50, r: 7, kind: 'scope', label: '4' },
              { x: 42, y: 66, r: 7, kind: 'scope', label: '5' }, { x: 58, y: 66, r: 7, kind: 'scope', label: '6' },
            ],
            arrows: [[0, 1, 'compare'], [2, 3, 'compare'], [4, 5, 'compare']],
          },
        },
        {
          id: 'lateral',
          title: 'Check the lateral bases',
          instruction: 'Ask the patient to lift an arm and listen in each mid-axillary line. Two quick placements.',
          assessing: 'Basal and lateral air entry missed from behind.',
          normal: 'Good air entry at both bases.',
          soap: 'good air entry at the bases',
          demo: {
            view: 'torso-front', caption: 'One placement each side, mid-axillary',
            // Front view: the patient's left is on the viewer's right.
            marks: [{ x: 26, y: 58, r: 7, kind: 'scope', label: 'R' }, { x: 74, y: 58, r: 7, kind: 'scope', label: 'L' }],
            arrows: [[0, 1, 'compare']],
          },
        },
      ],
      optional: [
        { title: 'Percussion', why: 'Adds real value with suspected effusion or consolidation; slow as a routine.' },
        { title: 'Tactile fremitus', why: 'Low yield in a normal chest and easy to perform unconvincingly.' },
        { title: 'Egophony / whispered pectoriloquy', why: 'Only when you already suspect consolidation.' },
      ],
      soapPrefix: 'Resp:',
    },

    abdominal: {
      id: 'abdominal',
      title: 'Abdominal',
      blurb: 'Inspect, auscultate, percuss, palpate — in that order.',
      duration: '~60 seconds',
      position: 'Supine, knees slightly flexed, arms at the sides. Expose the abdomen, drape the rest. Warm hands.',
      steps: [
        {
          id: 'inspect',
          title: 'Inspect',
          instruction: 'Look across the abdomen at eye level. Note contour, scars, distension, and any visible pulsation or peristalsis.',
          assessing: 'Contour, scars, distension.',
          normal: 'Flat, no scars, no distension.',
          soap: 'abdomen flat, no scars or distension',
          demo: { view: 'abdomen', caption: 'Look across at eye level', marks: [{ x: 50, y: 50, r: 30, kind: 'zone', label: 'abdomen' }] },
        },
        {
          id: 'auscultate',
          title: 'Auscultate — before you press',
          instruction: 'Diaphragm on the abdomen. Listen in one or two places for bowel sounds. Palpating first can change what you hear, which is why this comes second.',
          assessing: 'Presence and character of bowel sounds.',
          normal: 'Bowel sounds present and normoactive.',
          soap: 'bowel sounds present',
          demo: { view: 'abdomen', caption: 'Auscultation precedes percussion and palpation', marks: [{ x: 56, y: 56, r: 8, kind: 'scope', label: '1' }] },
        },
        {
          id: 'percuss',
          title: 'Percuss lightly',
          instruction: 'A few taps in each quadrant.',
          assessing: 'Tympany versus dullness; gross organomegaly.',
          normal: 'Tympanic throughout, no shifting dullness.',
          soap: 'tympanic to percussion',
          demo: {
            view: 'abdomen', caption: 'A few taps per quadrant', quadrants: true,
            marks: [
              { x: 38, y: 38, r: 6, kind: 'tap', label: '1' }, { x: 62, y: 38, r: 6, kind: 'tap', label: '2' },
              { x: 62, y: 62, r: 6, kind: 'tap', label: '3' }, { x: 38, y: 62, r: 6, kind: 'tap', label: '4' },
            ],
          },
        },
        {
          id: 'palpate',
          title: 'Palpate — light, then deeper',
          instruction: 'Ask where it hurts and start in the opposite quadrant. Light palpation in all four quadrants, watching the patient\'s face, then deeper if tolerated.',
          assessing: 'Tenderness, guarding, masses.',
          normal: 'Soft, non-tender, no guarding, no masses.',
          soap: 'soft, non-tender, non-distended, no guarding or masses',
          demo: {
            view: 'abdomen', caption: 'Start away from the pain', quadrants: true,
            marks: [
              { x: 38, y: 38, r: 8, kind: 'hand', label: '1' }, { x: 62, y: 38, r: 8, kind: 'hand', label: '2' },
              { x: 62, y: 62, r: 8, kind: 'hand', label: '3' }, { x: 38, y: 62, r: 8, kind: 'hand', label: '4' },
            ],
            arrows: [[0, 1], [1, 2], [2, 3]],
          },
        },
      ],
      optional: [
        { title: 'Rebound and guarding', why: 'Only when peritonitis is a real question; uncomfortable and not a routine screen.' },
        { title: 'Liver and spleen edges', why: 'Worth adding for suspected organomegaly.' },
        { title: 'Murphy / McBurney / psoas signs', why: 'Condition-specific. Perform when the history points there, not by default.' },
        { title: 'CVA tenderness', why: 'Quick and worth adding for flank pain or suspected pyelonephritis.' },
      ],
      soapPrefix: 'Abd:',
    },

    heent: {
      id: 'heent',
      title: 'HEENT & neck',
      blurb: 'The short version: face, eyes, ears/nose, mouth, neck.',
      duration: '~60–75 seconds',
      position: 'Patient seated, at eye level, adequate light.',
      steps: [
        {
          id: 'head',
          title: 'Head and face',
          instruction: 'Look at the face and scalp. Note symmetry and any lesions or swelling.',
          assessing: 'Symmetry, trauma, lesions.',
          normal: 'Normocephalic, atraumatic, face symmetric.',
          soap: 'normocephalic, atraumatic',
          demo: { view: 'head', caption: 'Symmetry first', marks: [{ x: 50, y: 40, r: 24, kind: 'zone', label: 'face' }] },
        },
        {
          id: 'eyes',
          title: 'Eyes',
          instruction: 'Look at the conjunctivae and sclerae. Check pupils with a light, then track your finger through an H to test eye movements.',
          assessing: 'Conjunctival pallor, scleral icterus, pupil reaction, extraocular movements.',
          normal: 'Conjunctivae clear, sclerae anicteric, PERRL, EOM intact.',
          soap: 'conjunctivae clear, sclerae anicteric, PERRL, EOM intact',
          demo: {
            view: 'head', caption: 'Pupils, then an H for eye movements',
            // Facing the patient: their left eye is on the viewer's right.
            marks: [{ x: 41, y: 37, r: 6, kind: 'look', label: 'R' }, { x: 59, y: 37, r: 6, kind: 'look', label: 'L' }],
            path: 'H',
          },
        },
        {
          id: 'earsnose',
          title: 'Ears and nose',
          instruction: 'Look at the external ears. Otoscope briefly in each canal if it is relevant. Lift the tip of the nose and look at the nares.',
          assessing: 'Canal and drum, nasal mucosa and patency.',
          normal: 'External ears normal, canals clear, TMs pearly grey; nares patent without discharge.',
          soap: 'ear canals clear, TMs normal; nares patent',
          demo: {
            view: 'head', caption: 'Both ears, then the nares',
            marks: [{ x: 30, y: 44, r: 6, kind: 'look', label: '1' }, { x: 70, y: 44, r: 6, kind: 'look', label: '2' }, { x: 50, y: 50, r: 6, kind: 'look', label: '3' }],
          },
        },
        {
          id: 'mouth',
          title: 'Mouth and oropharynx',
          instruction: 'Ask the patient to open and say "ah". Look at the mucosa, tongue, tonsils, and posterior pharynx. Use a light.',
          assessing: 'Moisture, erythema, exudate, tonsillar enlargement.',
          normal: 'Oral mucosa moist, oropharynx without erythema or exudate.',
          soap: 'oropharynx without erythema or exudate, mucous membranes moist',
          demo: { view: 'head', caption: '"Open and say ah"', marks: [{ x: 50, y: 58, r: 9, kind: 'look', label: 'ah' }] },
        },
        {
          id: 'neck',
          title: 'Neck',
          instruction: 'Palpate the cervical chains with both hands, then the thyroid. Note any stiffness.',
          assessing: 'Lymphadenopathy, thyroid size, neck suppleness.',
          normal: 'Neck supple, no lymphadenopathy, thyroid not enlarged.',
          soap: 'neck supple, no lymphadenopathy',
          demo: {
            view: 'head', caption: 'Both hands down the cervical chains',
            marks: [{ x: 36, y: 70, r: 7, kind: 'hand' }, { x: 64, y: 70, r: 7, kind: 'hand' }],
            arrows: [[0, 1, 'compare']],
          },
        },
      ],
      optional: [
        { title: 'Fundoscopy', why: 'Slow, hard to do well, and rarely changes a CSE note.' },
        { title: 'Visual acuity', why: 'Add when the complaint is visual.' },
        { title: 'Weber and Rinne', why: 'Add for hearing loss, not as a screen.' },
        { title: 'Sinus percussion', why: 'Quick to add for facial pain or suspected sinusitis.' },
      ],
      soapPrefix: 'HEENT:',
    },

    msk: {
      id: 'msk',
      title: 'Musculoskeletal',
      blurb: 'One framework for any joint: look, feel, move, strength.',
      duration: '~45–60 seconds per region',
      position: 'Expose and compare with the other side. Ask about pain before you touch.',
      regions: ['Shoulder', 'Elbow', 'Wrist / hand', 'Hip', 'Knee', 'Ankle / foot', 'Back'],
      steps: [
        {
          id: 'look',
          title: 'Look',
          instruction: 'Inspect the joint and compare it with the other side. Note swelling, deformity, redness, muscle wasting.',
          assessing: 'Swelling, deformity, erythema, asymmetry.',
          normal: 'No swelling, deformity, or erythema; symmetric with the other side.',
          soap: 'no swelling, deformity, or erythema',
          demo: {
            view: 'joint', caption: 'Always compare with the other side',
            marks: [{ x: 32, y: 48, r: 14, kind: 'zone', label: 'R' }, { x: 68, y: 48, r: 14, kind: 'zone', label: 'L' }],
            arrows: [[0, 1, 'compare']],
          },
        },
        {
          id: 'feel',
          title: 'Feel',
          instruction: 'Ask where it hurts, then palpate — starting away from that point. Feel for warmth, tenderness, and effusion over the joint line.',
          assessing: 'Warmth, tenderness, effusion.',
          normal: 'No warmth, tenderness, or effusion.',
          soap: 'no tenderness, warmth, or effusion',
          demo: { view: 'joint', caption: 'Start away from the painful point', marks: [{ x: 50, y: 48, r: 10, kind: 'hand', label: 'joint line' }] },
        },
        {
          id: 'move',
          title: 'Move',
          instruction: 'Ask the patient to move the joint through its range first. Only then move it yourself, gently, if active movement was limited.',
          assessing: 'Active then passive range; pain through the arc.',
          normal: 'Full active and passive range of motion without pain.',
          soap: 'full range of motion without pain',
          demo: { view: 'joint', caption: 'Active first, then passive', marks: [{ x: 50, y: 48, r: 12, kind: 'move', label: 'ROM' }], path: 'arc' },
        },
        {
          id: 'strength',
          title: 'Strength and neurovascular',
          instruction: 'Resisted movement in the main directions, compared side to side. Check distal pulse and sensation.',
          assessing: 'Power against resistance; distal circulation and sensation.',
          normal: 'Strength 5/5 and symmetric; distally neurovascularly intact.',
          soap: 'strength 5/5, neurovascularly intact distally',
          demo: {
            view: 'joint', caption: 'Resisted, and compared side to side',
            marks: [{ x: 32, y: 48, r: 10, kind: 'move', label: 'R' }, { x: 68, y: 48, r: 10, kind: 'move', label: 'L' }],
            arrows: [[0, 1, 'compare']],
          },
        },
      ],
      optional: [
        { title: 'Region-specific special tests', why: 'Only when the history points to one — a special test performed at random is not informative.' },
        { title: 'Gait', why: 'Quick and high value for hip, knee, ankle, and back.' },
        { title: 'Straight leg raise', why: 'Add for back pain with radicular features.' },
      ],
      soapPrefix: 'MSK:',
    },
  };

  window.PCM_EXAM_SEQUENCES = EXAMS;
})();
