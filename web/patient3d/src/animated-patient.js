/**
 * Shared runtime for authored, skinned patient assets.
 *
 * This adapter never edits skin textures, hides a watermark, invents findings,
 * chooses a case, or credits an examination. Those decisions belong to the app.
 * The exported asset's manifest must document every facial control used here.
 * A loaded skeleton alone does not establish an animation capability.
 */
import {SceneLoader} from '@babylonjs/core/Loading/sceneLoader.js';
import {Bone} from '@babylonjs/core/Bones/bone.js';
import {Skeleton} from '@babylonjs/core/Bones/skeleton.js';
import {RegisterAnimatable} from '@babylonjs/core/Animations/animatable.pure.js';
RegisterAnimatable();
import {TransformNode} from '@babylonjs/core/Meshes/transformNode.js';
import {Mesh} from '@babylonjs/core/Meshes/mesh.js';
import {Quaternion, Vector3} from '@babylonjs/core/Maths/math.vector.js';
import '@babylonjs/loaders/glTF/2.0/glTFLoader.js';
import '@babylonjs/loaders/glTF/glTFFileLoader.js';

const clamp = (value, min = 0, max = 1) => Math.max(min, Math.min(max, Number(value) || 0));
const DEFAULT_CONTROLS = Object.freeze({
  blink: ['PCM_Blink'], speech: ['PCM_Speech'], discomfort: ['PCM_Discomfort'], concern: ['PCM_Concern'],
  warmth: ['Warmth'], gazeLeft: ['PCM_GazeLeft'], gazeRight: ['PCM_GazeRight'],
  gazeUp: ['PCM_GazeUp'], gazeDown: ['PCM_GazeDown'],
});

/** Pure control policy, exported so evidence/voice boundaries can be tested. */
export function patientAnimationIntent(state = {}, now = 0, transient = {}) {
  const seconds = Math.max(0, Number(now) || 0) / 1000;
  const motion = !state.reducedMotion && state.phase === 'encounter';
  // Animation intensity is derived only from the public, already-disclosed affect.
  // A region selection or an exam never fabricates a tenderness/pain reaction.
  const discomfort = clamp(state.affect?.discomfort);
  const suppliedRate = Number(state.respiratoryRate);
  const respiratoryRate = Number.isFinite(suppliedRate) && suppliedRate >= 4 && suppliedRate <= 60 ? suppliedRate : 16;
  const style=state.demeanor?.style||'calm';
  const tension=clamp(state.demeanor?.tension);
  const engagement=state.demeanor?.authored?clamp(state.demeanor?.engagement):.65;
  const restrained=['guarded','tired','frustrated'].includes(style);
  // Brief changes in an already-disclosed symptom, with longer resting periods.
  // This changes expression strength, not pain severity, location or findings.
  const regionOffset={head:1.3,chest:3.7,abdomen:2.1,flank:4.8,back:.7}[state.affect?.guardRegion]||0;
  const painMoment=Math.sin(seconds*.37+regionOffset)+.26*Math.sin(seconds*.71+regionOffset);
  const pulse=motion?.58+.42*Math.pow(clamp((painMoment-.36)/.88),3):.58;
  const phase = (seconds + .83) % 4.93;
  const blink = motion && phase < .19 ? Math.sin(phase / .19 * Math.PI) : 0;
  // Speech begins and stops with actual playback state. This is amplitude-style
  // articulation, not phoneme/viseme alignment and never starts from reply text.
  const speech = motion && state.speaking === true
    ? (.26 + .52 * Math.abs(Math.sin(seconds * 10.7))) * (.74 + .26 * Math.sin(seconds * 3.4) ** 2)
    : 0;
  const acknowledge = motion && now < (transient.acknowledgeUntil || 0)
    ? Math.sin((1 - clamp(((transient.acknowledgeUntil || 0) - now) / 850)) * Math.PI * 2) * .027 : 0;
  const attentive = state.listening === true || state.speaking === true;
  return {
    warmth: motion && state.demeanor?.authored && ['friendly','cheerful','warm'].includes(style) && !state.speaking ? (.22 + .08*Math.sin(seconds*.13))*(1-discomfort)*(1-tension) : 0,
    blink, speech, discomfort: discomfort * pulse * (state.speaking?.86:1), concern:Math.max(clamp(state.affect?.concern),tension*.60),
    breath: motion ? Math.sin(seconds * Math.PI * 2 * respiratoryRate / 60) : 0,
    headPitch: motion ? Math.sin(seconds * .49) * (restrained?.003:.006) + acknowledge*(.75+engagement*.35) : 0,
    headYaw: motion ? Math.sin(seconds * .28) * (attentive ? .006 : .017) * (restrained?.6:1) * (1-discomfort*.7) : 0,
    headRoll: motion ? Math.sin(seconds * .41) * (restrained?.003:.005) * (1-discomfort*.5) : 0,
    gazeX: motion ? Math.sin(seconds * .31) * (attentive ? .008 : .04) : 0,
    gazeY: motion ? Math.sin(seconds * .43) * .015 : 0,
    motion,
  };
}

function nowMs() { return globalThis.performance?.now?.() || Date.now(); }
function nodeRest(node) {
  if (!node) return null;
  node.rotationQuaternion ||= Quaternion.FromEulerVector(node.rotation);
  return {node, position: node.position.clone(), scaling: node.scaling.clone(), rotation: node.rotationQuaternion.clone()};
}
function restore(entry) {
  if (!entry) return;
  entry.node.position.copyFrom(entry.position);
  entry.node.scaling.copyFrom(entry.scaling);
  entry.node.rotationQuaternion.copyFrom(entry.rotation);
}
function importedNode(container, exactName) {
  return [...container.transformNodes, ...container.meshes].find(node => node.name === exactName) ||
    container.skeletons.flatMap(skeleton => skeleton.bones)
      .find(bone => bone.name === exactName)?.getTransformNode() || null;
}
// Prove that an imported eye bone controls actual eye vertices. A similarly
// named FACS helper with no skin influence does not establish this capability.
function skinnedEyeNode(container, boneName) {
  for (const skeleton of container.skeletons) {
    const bone = skeleton.bones.find(item => item.name === boneName);
    if (!bone?.getTransformNode()) continue;
    const index = bone.getIndex();
    for (const mesh of container.meshes) {
      if (mesh.skeleton !== skeleton || !/eye/i.test(mesh.name)) continue;
      for (const suffix of ['', 'Extra']) {
        const indices = mesh.getVerticesData('matricesIndices' + suffix);
        const weights = mesh.getVerticesData('matricesWeights' + suffix);
        if (indices && weights && indices.some((value, i) => value === index && weights[i] > .005)) return bone.getTransformNode();
      }
    }
  }
  return null;
}
// Whole-body garments have no per-arm mesh names. Classify the hit triangle
// from its actual skin weights before falling back to the posed body landmarks.
function skinnedRegion(mesh, pickInfo) {
  if (!mesh.skeleton || !Number.isInteger(pickInfo?.faceId) || pickInfo.faceId < 0) return null;
  const indices = mesh.getIndices(), start = pickInfo.faceId * 3;
  if (!indices || start + 2 >= indices.length) return null;
  const totals = {MSK:0,HEENT:0,other:0};
  for (let corner=0;corner<3;corner++) {
    const vertex=indices[start+corner];
    for (const suffix of ['', 'Extra']) {
      const joints=mesh.getVerticesData('matricesIndices'+suffix), weights=mesh.getVerticesData('matricesWeights'+suffix);
      if(!joints || !weights)continue;
      for(let slot=0;slot<4;slot++){
        const index=vertex*4+slot, amount=Number(weights[index])||0;
        const bone=mesh.skeleton.bones.find(item=>item.getIndex()===joints[index]);
        const name=bone?.name||'';
        const region=/upper.?arm|lower.?arm|forearm|hand|finger|thumb|index|middle|ring|pinky|thigh|calf|shin|foot|toe|ball_[lr]/i.test(name)?'MSK':/head|neck/i.test(name)?'HEENT':'other';
        totals[region]+=amount/3;
      }
    }
  }
  if(totals.MSK>.5)return 'MSK';
  if(totals.HEENT>.5)return 'HEENT';
  return null;
}
function worldEyeRotation(entry, yaw, pitch, lookTarget) {
  if (!entry) return;
  // The imported eye bone's local forward axis is not assumed. Express yaw and
  // pitch in the room's right-handed world axes, conjugate into its current
  // parent frame, and preserve the exported rest orientation. This produces
  // gaze shifts instead of rotating the iris around an unknown local axis.
  const parent = entry.node.parent;
  const parentRotation = Quaternion.Identity();
  if (parent) { parent.computeWorldMatrix(true); parent.getWorldMatrix().decompose(undefined, parentRotation); }
  let aim = Quaternion.Identity();
  if (lookTarget) {
    entry.node.computeWorldMatrix(true);
    // The export manifest and actual skin inspection establish local Y as the
    // eye bone's forward axis. Face the conversation camera with restrained
    // vergence; do not chase a camera orbiting behind or far above the patient.
    const forward = Vector3.TransformNormal(Vector3.Up(), entry.node.getWorldMatrix()).normalize();
    const direction = lookTarget.subtract(entry.node.getAbsolutePosition()).normalize();
    const dot = Math.max(-1, Math.min(1, Vector3.Dot(forward, direction)));
    if (dot > .75) {
      Quaternion.FromUnitVectorsToRef(forward, direction, aim);
      const angle = Math.acos(dot), maxAngle = .22;
      if (angle > maxAngle) aim = Quaternion.Slerp(Quaternion.Identity(), aim, maxAngle / angle);
    }
  }
  const delta = Quaternion.FromEulerAngles(pitch, yaw, 0).multiply(aim);
  entry.node.rotationQuaternion.copyFrom(Quaternion.Inverse(parentRotation).multiply(delta).multiply(parentRotation).multiply(entry.rotation));
}
function normalizeNames(value) { return Array.isArray(value) ? value : typeof value === 'string' ? [value] : []; }

/**
 * @returns controller with ready: Promise<boolean>. A failure resolves false and
 * removes every partly loaded trial object; retain the existing patient fallback.
 * No scene object is displayed until successful loading and shader preparation.
 */
export function createAnimatedPatient(scene, options = {}) {
  const started = nowMs(), label = options.label || 'Patient';
  let appearanceSignature = '';
  const ownedResources = [];
  const status = (state, message = '') => options.onStatus?.({state, message});
  let container = null, disposed = false, failed = false, wanted = false, loaded = false;
  let state = {}, last = 0, examinedAt = 0, acknowledgeUntil = 0, posture = null, poseTransition = null;
  const root = new TransformNode(options.rootName || 'Authored patient', scene);
  root.setEnabled(false);
  const controls = {}, body = {}, landmarkNodes = {}, poseRoots = new Map();
  const metrics = {loadMs: null, meshCount: 0, triangles: 0, vertices: 0, textureCount: 0, animationFrames: 0};
  const capabilities = {
    trial: false, characterCount: 1, presentation: options.presentation || 'neutral', ...(options.capabilityMetadata || {}),
    blink: false, speech: false, discomfort: false, concern: false, gaze: false,
    breathing: false, headMovement: false, supportedPostures: [],
    mouthSynchronization: 'Unavailable until an exported speech control is verified.',
    findings: 'No clinical evidence is generated by this visual adapter.',
  };

  function desiredPose() { return state.posture === 'supine' ? 'supine' : 'seated'; }
  function supported() { return loaded && capabilities.supportedPostures.includes(desiredPose()); }
  function eligible() {
    return !!options.isEligible?.(state) && (!options.allowedCaseIds || options.allowedCaseIds.includes(state.caseId));
  }
  function updateAppearance() {
    if (!loaded || !options.applyAppearance) return;
    const signature = JSON.stringify(state.appearance || {});
    if (signature === appearanceSignature) return;
    options.applyAppearance(container, state.appearance || {});
    appearanceSignature = signature;
  }
  function show() {
    const canShow = wanted && eligible() && supported() && !disposed && !failed;
    root.setEnabled(canShow);
    for (const [name, node] of poseRoots) node.setEnabled(name === desiredPose());
    return canShow;
  }
  function write(name, value) {
    for (const target of controls[name] || []) target.influence = clamp(value);
  }
  function zeroMotion() {
    for (const name of Object.keys(controls)) write(name, 0);
    for (const entry of Object.values(body)) restore(entry);
  }
  function applyPosture() {
    if (!loaded) return;
    const desired = desiredPose();
    if (desired === posture) return;
    const previous = posture;
    posture = desired;
    zeroMotion();
    const poseNodes = [...new Set((container?.animationGroups || []).flatMap(group => group.targetedAnimations.map(item => item.target)))]
      .filter(node => node?.position?.clone && node?.scaling?.clone && node?.rotation);
    const before = poseNodes.map(nodeRest);
    poseTransition = null;
    // Optional exported pose clips are exact named, artist-verified poses. Clip
    // evaluation occurs at its authored first frame, never an guessed rig bend.
    const clipName = options.postureClips?.[posture];
    if (clipName) {
      for (const group of container?.animationGroups || []) group.stop();
      const group = container?.animationGroups.find(item => item.name === clipName);
      if (group) {
        group.start(false); group.goToFrame(group.from); group.pause();
        for (const [key, entry] of Object.entries(body)) body[key] = nodeRest(entry?.node);
        if (previous && state.phase === 'encounter' && !state.reducedMotion && (options.postureTransitionMs || 0) > 0) {
          const after = poseNodes.map(nodeRest);
          poseTransition = {started:nowMs(),duration:options.postureTransitionMs,before,after,fromVisuals:options.poseControlValues?.(previous)||{},toVisuals:options.poseControlValues?.(posture)||{}};
          for (const entry of before) restore(entry);
        }
      }
    }
    const visuals=poseTransition?poseTransition.fromVisuals:(options.poseControlValues?.(posture)||{});
    for(const [name,value]of Object.entries(visuals))write(name,value);
  }
  const controller = {
    root, metrics, capabilities, ready: null,
    get loaded() { return loaded && !disposed && !failed; },
    get visible() { return root.isEnabled(); },
    get postureSupported() { return supported(); },
    // World-space landmarks come from the imported rig, not the dimensions of
    // the previous simplified patient. Call again after a verified pose change.
    get anchors() {
      if (!loaded) return null;
      const point = name => {
        const node = landmarkNodes[name];
        if (!node) return null;
        node.computeWorldMatrix(true); return node.getAbsolutePosition().clone();
      };
      const left = point('eyeLeft'), right = point('eyeRight');
      const face = point('face') || (left && right ? left.add(right).scale(.5).add(new Vector3(0, -.025, 0))
        : point('head')?.add(new Vector3(0, .08, 0)));
      const chest = point('chest'), abdomen = point('abdomen'), lap = point('lap'), shoulder = point('neck');
      return {face, chest, abdomen, lap, shoulder,
        patient: face && abdomen ? Vector3.Lerp(abdomen, face, .58) : face};
    },
    setEnabled(value) { wanted = value === true; return show(); },
    update(next) {
      const nextState = next || {};
      if (state.sessionId && state.sessionId !== nextState.sessionId) {
        acknowledgeUntil = 0; examinedAt = 0; zeroMotion();
      }
      state = nextState;
      applyPosture();
      updateAppearance();
      show();
      return {visible: controller.visible, supported: supported(), posture: desiredPose()};
    },
    acknowledge() { if (state.phase === 'encounter') acknowledgeUntil = nowMs() + 850; },
    examine(command) {
      if (state.phase !== 'encounter' || !command?.maneuver_id || !controller.visible) return false;
      // A small acknowledgment is cooperation, not a finding. The app still
      // validates the action, authorizes its findings and owns all event IDs.
      examinedAt = nowMs();
      acknowledgeUntil = examinedAt + 850;
      return true;
    },
    animate(now = nowMs()) {
      if (!controller.visible) return;
      const dt = Math.min(.1, Math.max(0, (now - (last || now)) / 1000));
      last = now;
      const intention = patientAnimationIntent(state, now, {acknowledgeUntil, examinedAt});
      // Do not leave an open mouth after speech interruption or after note phase.
      // Other expression targets use a brief, frame-rate-independent transition.
      for (const [name, goal] of [['blink', intention.blink], ['speech', intention.speech], ['discomfort', intention.discomfort], ['concern', intention.concern], ['warmth', intention.warmth]]) {
        for (const target of controls[name] || []) {
          const immediate = name === 'blink' || (name === 'speech' && !intention.speech) || !intention.motion;
          const rate=name==='concern'?2.4:name==='discomfort'?5.5:18;
          target.influence = immediate ? goal : target.influence + (goal - target.influence) * (1 - Math.exp(-dt * rate));
        }
      }
      const gaze = options.gazeIntent?.(state, now) || {x:intention.gazeX,y:intention.gazeY};
      const gazeScale = options.gazeMorphRadians || 1;
      write('gazeLeft', Math.max(0, -gaze.x / gazeScale));
      write('gazeRight', Math.max(0, gaze.x / gazeScale));
      write('gazeUp', Math.max(0, gaze.y / gazeScale));
      write('gazeDown', Math.max(0, -gaze.y / gazeScale));
      if (poseTransition) {
        const u=state.reducedMotion?1:clamp((now-poseTransition.started)/poseTransition.duration), eased=u*u*(3-2*u);
        for(let i=0;i<poseTransition.before.length;i++){
          const from=poseTransition.before[i],to=poseTransition.after[i],node=to.node;
          node.position.copyFrom(Vector3.Lerp(from.position,to.position,eased));
          node.scaling.copyFrom(Vector3.Lerp(from.scaling,to.scaling,eased));
          node.rotationQuaternion.copyFrom(Quaternion.Slerp(from.rotation,to.rotation,eased));
        }
        for(const [name,to]of Object.entries(poseTransition.toVisuals||{}))write(name,(poseTransition.fromVisuals[name]||0)+(to-(poseTransition.fromVisuals[name]||0))*eased);
        if(u>=1)poseTransition=null;
        metrics.animationFrames++;return;
      }
      for (const entry of Object.values(body)) restore(entry);
      if (body.head) body.head.node.rotationQuaternion.copyFrom(body.head.rotation.multiply(
        Quaternion.FromEulerAngles(intention.headPitch, intention.headYaw, intention.headRoll)));
      if (body.chest) {
        body.chest.node.scaling.z = body.chest.scaling.z * (1 + intention.breath * .0025);
        body.chest.node.rotationQuaternion.copyFrom(body.chest.rotation.multiply(
          Quaternion.FromEulerAngles(intention.breath * .0017, 0, 0)));
      }
      if (body.eyeLeft && body.eyeRight) {
        const lookTarget = intention.motion ? options.getLookTarget?.() : null;
        worldEyeRotation(body.eyeLeft, intention.gazeX, intention.gazeY, lookTarget);
        worldEyeRotation(body.eyeRight, intention.gazeX, intention.gazeY, lookTarget);
      }
      metrics.animationFrames++;
    },
    ownsMesh(mesh) { return !!mesh && mesh.isEnabled?.() !== false && (mesh === root || mesh.isDescendantOf?.(root)) && controller.visible; },
    regionAt(point, mesh, pickInfo) {
      if (!controller.ownsMesh(mesh) || !point) return null;
      const weightedRegion = skinnedRegion(mesh, pickInfo);
      if (weightedRegion) return weightedRegion;
      const name = mesh.name || '';
      if (/eyes?|teeth|tongue|hair|brow|lash/i.test(name)) return 'HEENT';
      const p = Vector3.TransformCoordinates(point, root.getWorldMatrix().clone().invert());
      const marks = controller.anchors;
      const localY = p => p && Vector3.TransformCoordinates(p, root.getWorldMatrix().clone().invert()).y;
      const a = options.anchors || {
        faceY: localY(marks?.face) ?? 2.05,
        shoulderY: localY(marks?.shoulder) ?? 1.82,
        abdomenY: marks?.chest && marks?.abdomen ? (localY(marks.chest) + localY(marks.abdomen)) / 2 : 1.38,
        lapY: localY(marks?.lap) ?? 1.12,
      };
      if (desiredPose() === 'supine') {
        if (!marks?.face || !marks?.lap || !marks?.abdomen || !marks?.chest) return 'General';
        // Project onto the authored body axis; a supine body's Y coordinate is
        // its elevation above the table, not its location from head to toe.
        const axis = marks.face.subtract(marks.lap).normalize();
        const along = Vector3.Dot(point.subtract(marks.lap), axis);
        const project = mark => Vector3.Dot(mark.subtract(marks.lap), axis);
        const center = marks.lap.add(axis.scale(along));
        if (along > (project(marks.face) + project(marks.chest)) / 2) return 'HEENT';
        if (along < -.03 || Math.abs(point.x - center.x) > .28) return 'MSK';
        return along < (project(marks.abdomen) + project(marks.chest)) / 2 ? 'Abdomen' : 'Heart';
      }
      if (p.y > a.shoulderY) return 'HEENT';
      if (Math.abs(p.x) > .29 || p.y < a.lapY) return 'MSK';
      return p.y < a.abdomenY ? 'Abdomen' : 'Heart';
    },
    dispose() {
      if (disposed) return;
      disposed = true; wanted = false; loaded = false;
      container?.dispose(); for (const resource of ownedResources) resource?.dispose?.(); root.dispose();
    },
  };

  async function load() {
    status('loading', `Preparing ${label.toLowerCase()}…`);
    const asset = options.assetUrl;
    const split = asset.lastIndexOf('/');
    let timer;
    try {
      if (typeof Bone !== 'function' || typeof Skeleton !== 'function') throw new Error('Babylon skeletal runtime is unavailable.');
      const importPromise = SceneLoader.LoadAssetContainerAsync(asset.slice(0, split + 1), asset.slice(split + 1), scene);
      // A late completion after timeout must never leave an unowned patient in
      // the room. AssetContainer permits this without temporarily adding meshes.
      importPromise.then(result => { if (failed || disposed) result.dispose(); }).catch(() => {});
      container = await Promise.race([importPromise, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} did not finish loading.`)), options.timeoutMs || 30000);
      })]);
      clearTimeout(timer);
      if (disposed) { container.dispose(); return false; }
      if (!container.meshes.some(mesh => mesh.getTotalVertices() > 0)) throw new Error(`${label} asset contains no patient geometry.`);
      const exportedMorphTargetNames = [...new Set(container.meshes.map(mesh=>mesh.morphTargetManager).filter(Boolean))]
        .flatMap(manager=>Array.from({length:manager.numTargets},(_,i)=>manager.getTarget(i).name));
      const runtimeGeometry = options.prepareGeometry?.(container, scene) || {};
      const controlNames = {...DEFAULT_CONTROLS, ...(options.controlNames || {})};
      const managers = new Set(container.meshes.map(mesh => mesh.morphTargetManager).filter(Boolean));
      for (const name of Object.keys(controlNames)) {
        const names = normalizeNames(controlNames[name]);
        controls[name] = [...managers].flatMap(manager => Array.from({length: manager.numTargets}, (_, i) => manager.getTarget(i)))
          .filter(target => names.includes(target.name));
      }
      // Keep one stable shader configuration as blinking and speech switch.
      for (const manager of managers) {
        const activeNames = new Set(Object.values(controls).flat().map(target => target.name));
        const possible = Array.from({length: manager.numTargets}, (_, i) => manager.getTarget(i))
          .filter(target => activeNames.has(target.name) || target.influence > 0).length;
        if (possible) manager.numMaxInfluencers = possible;
      }
      // Exact rig nodes must be verified in the export manifest. Absence means
      // unsupported, not a best-guess lookup that bends a facial control bone.
      body.head = nodeRest(importedNode(container, options.rigNodes?.head || 'head'));
      body.chest = nodeRest(importedNode(container, options.rigNodes?.chest || 'spine.003'));
      const landmarks = {eyeLeft: 'eyeball.L', eyeRight: 'eyeball.R', head: 'head',
        neck: 'neck', chest: 'spine.003', abdomen: 'spine.001', lap: 'spine', ...(options.landmarkNodes || {})};
      for (const [role, name] of Object.entries(landmarks)) landmarkNodes[role] = importedNode(container, name);
      for (const [name, nodeName] of Object.entries(options.postureRoots || {})) {
        const node = importedNode(container, nodeName);
        if (node) poseRoots.set(name, node);
      }
      const declaredPostures = options.supportedPostures || ['seated'];
      capabilities.supportedPostures = declaredPostures.filter(name => {
        if (poseRoots.size) return poseRoots.has(name);
        if (options.postureClips?.[name]) return container.animationGroups.some(group => group.name === options.postureClips[name]);
        return name === 'seated';
      });
      for (const name of ['blink', 'speech', 'discomfort', 'concern', 'warmth']) capabilities[name] = !!controls[name]?.length;
      body.eyeLeft = nodeRest(skinnedEyeNode(container, options.rigNodes?.eyeLeft || 'eyeball.L'));
      body.eyeRight = nodeRest(skinnedEyeNode(container, options.rigNodes?.eyeRight || 'eyeball.R'));
      capabilities.gaze = !!(body.eyeLeft && body.eyeRight) || !!(controls.gazeLeft?.length || controls.gazeRight?.length);
      capabilities.gazeMechanism = body.eyeLeft && body.eyeRight
        ? 'Camera-directed eye contact, capped at 12.6 degrees, with small movements of two verified skinned eye bones.'
        : capabilities.gaze ? runtimeGeometry.gazeMechanism || 'Verified exported directional eye morphs.' : 'No verified exported eye movement control.';
      capabilities.runtimeGeometry = runtimeGeometry;
      capabilities.breathing = !!body.chest;
      capabilities.headMovement = !!body.head;
      capabilities.mouthSynchronization = capabilities.speech
        ? 'Playback-gated procedural mouth opening; no phoneme or viseme alignment.'
        : 'No verified exported mouth control; spoken audio remains available.';
      capabilities.exportedMorphTargets = exportedMorphTargetNames;
      capabilities.exportedAnimationGroups = container.animationGroups.map(group => group.name);
      for (const key of options.requiredControls || []) if (!capabilities[key]) throw new Error(`Required ${key} control is missing from ${label.toLowerCase()}.`);
      for (const pose of options.requiredPostures || []) if (!capabilities.supportedPostures.includes(pose)) throw new Error(`Required ${pose} pose is missing from ${label.toLowerCase()}.`);
      for (const key of options.requiredLandmarks || []) if (!landmarkNodes[key]) throw new Error(`Required ${key} landmark is missing from ${label.toLowerCase()}.`);
      for (const name of options.requiredMeshes || []) if (!container.meshes.some(mesh => mesh.name === name)) throw new Error(`Required ${name} mesh is missing from ${label.toLowerCase()}.`);
      if (options.prepare) ownedResources.push(...(await options.prepare(container, scene) || []));
      for (const mesh of container.meshes) {
        if(options.preciseSkinnedPicking && mesh.skeleton && mesh.getTotalVertices()>0){
          const proxy = new Mesh(`${mesh.name} picking surface`,scene);
          proxy.setEnabled(false);proxy.isPickable=false;proxy.material=mesh.material;
          proxy.setVerticesData('position',mesh.getVerticesData('position').slice(),true);
          if(mesh.getIndices())proxy.setIndices(mesh.getIndices());
          ownedResources.push(proxy);
          const originalIntersects=mesh.intersects;
          mesh.intersects=function(ray,fastCheck,trianglePredicate,onlyBoundingInfo=false,worldToUse,skipBoundingInfo=false){
            const positions=mesh.getPositionData(true,true);
            if(!positions)return originalIntersects.call(mesh,ray,fastCheck,trianglePredicate,onlyBoundingInfo,worldToUse,skipBoundingInfo);
            proxy.updateVerticesData('position',positions,true);proxy.refreshBoundingInfo();
            const hit=proxy.intersects(ray,fastCheck,trianglePredicate,onlyBoundingInfo,worldToUse||mesh.getWorldMatrix(),skipBoundingInfo);
            if(hit.hit)hit.pickedMesh=mesh;
            return hit;
          };
        }
        metrics.vertices += mesh.getTotalVertices();
        metrics.triangles += (mesh.getTotalIndices() || 0) / 3;
        mesh.receiveShadows = true;
        if (mesh.getTotalVertices() > 0) options.shadowGenerator?.addShadowCaster(mesh);
      }
      metrics.meshCount = container.meshes.filter(mesh => mesh.getTotalVertices() > 0).length;
      metrics.textureCount = container.textures.length;
      container.addAllToScene();
      for (const node of container.rootNodes) node.parent = root;
      // Compile while entry is still disabled. This prevents first speech/blink
      // from being an unreported shader stall in the timed encounter.
      const materials = new Map();
      for (const mesh of container.meshes) if (mesh.material && mesh.getTotalVertices() > 0) materials.set(mesh.material, mesh);
      await Promise.race([
        Promise.all([...materials].map(([material, mesh]) => material.forceCompilationAsync?.(mesh))),
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label} shaders did not become ready.`)), options.shaderTimeoutMs || 12000); }),
      ]);
      clearTimeout(timer);
      if (disposed) return false;
      loaded = true;
      metrics.loadMs = Math.round(nowMs() - started);
      applyPosture(); updateAppearance(); show();
      status('ready', options.readyMessage || `${label} ready.`);
      return true;
    } catch (error) {
      clearTimeout(timer); failed = true; loaded = false; root.setEnabled(false);
      container?.dispose(); for (const resource of ownedResources) resource?.dispose?.();
      const message = `${label} unavailable: ${error?.message || String(error)}`;
      console.error('[PCM patient asset]', message, error);
      status('error', message); options.onError?.(new Error(message));
      return false;
    }
  }
  controller.ready = load();
  return controller;
}
