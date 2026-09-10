import {SSAO2RenderingPipeline} from '@babylonjs/core/PostProcesses/RenderPipeline/Pipelines/ssao2RenderingPipeline.js';
import {createTechniquePatient} from './technique-patient.js';
import {conversationFrame,transitionConversationFrame} from './patient-framing.js';
import {createCameraNavigation} from './camera-navigation.js';
import {createTrialPatient} from './trial-patient.js';
import {createMPFBPatient} from './mpfb-patient.js';
import {createClinicalTable} from './clinical-table.js';
import {applyClinicalEnvironment} from './clinical-environment.js';
import {Engine} from '@babylonjs/core/Engines/engine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {Color3} from '@babylonjs/core/Maths/math.color.js';
import {Color4} from '@babylonjs/core/Maths/math.color.js';
import {HemisphericLight} from '@babylonjs/core/Lights/hemisphericLight.js';
import {RegisterRay} from '@babylonjs/core/Culling/ray.pure.js';
RegisterRay();
import {ShadowGenerator} from '@babylonjs/core/Lights/Shadows/shadowGenerator.js';
import {DirectionalLight} from '@babylonjs/core/Lights/directionalLight.js';
import {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode.js';
import {Quaternion} from '@babylonjs/core/Maths/math.vector.js';
import {SceneLoader} from '@babylonjs/core/Loading/sceneLoader.js';
import {PointerEventTypes} from '@babylonjs/core/Events/pointerEvents.js';
import '@babylonjs/loaders/glTF/2.0/glTFLoader.js';
import '@babylonjs/loaders/glTF/glTFFileLoader.js';
const started=performance.now(),canvas=document.getElementById('canvas'),V=(x,y,z)=>new Vector3(x,y,z),patientTarget=V(0,1.58,0),nodes=[];
let engine,scene,camera,seat,supine,publicState={},lesson=null,reference=null,tools=[],headPivot=null,headTarget=null,savedCamera=null,reply='',speechUntil=0;
const models={}, animated=[];let doorPivot,doorSurround,entrance=null,entered=false,desiredCamera=null,gestureAmount=0,nodUntil=0;const insideCamera=V(.37,1.99,2.25),insideTarget=V(0,1.65,0),outsideCamera=V(.25,1.48,6.95),outsideTarget=V(0,1.48,2.6);
let trialPatient=null,trialStatus='idle',trialMessage='',trialEntryWait=null,shadowCaster=null,trialGeneration=0;
let clinicalTable=null,techniqueStudio=null;
let cameraPreset='patient',poseCameraUntil=0,poseCameraFrom='seated',navigation=null;
let mpfbPatient=null,mpfbStatus='idle',mpfbMessage='',mpfbGeneration=0,mpfbBodyBuild=null;
function wantsMPFB(){return publicState.appearance?.model==='mpfb-public-patient'&&['female','male'].includes(publicState.appearance?.presentation);}
function currentPatient(){return wantsMPFB()?mpfbPatient:wantsTrial()?trialPatient:null;}
function patientNotice(status,message){mpfbStatus=status;mpfbMessage=message||'';if(!wantsMPFB())return;send({type:'pcm-patient-status',sessionId:publicState.sessionId,status,message:mpfbMessage});window.pcmPatientStatus?.({status,message:mpfbMessage});}
function ensureMPFB(){
 if(!wantsMPFB())return;
 const bodyBuild=['short-slender','standard','tall-full'].includes(publicState.appearance?.bodyBuild)?publicState.appearance.bodyBuild:null;
 const identity=publicState.appearance.presentation+':'+bodyBuild;
 if(mpfbBodyBuild!==identity){++mpfbGeneration;mpfbPatient?.dispose();mpfbPatient=null;mpfbStatus='idle';mpfbBodyBuild=identity;}
 if(mpfbPatient||mpfbStatus==='failed')return;
 patientNotice('loading',publicState.phase==='briefing'?'Preparing your patient. The encounter clock has not started.':'Preparing your patient. Conversation and examination controls remain available.');
 const generation=++mpfbGeneration;let current;
 try{current=createMPFBPatient(scene,{bodyBuild,presentation:publicState.appearance.presentation,getLookTarget:()=>camera.position,shadowGenerator:shadowCaster,onStatus:({state,message})=>{if(generation===mpfbGeneration)patientNotice(state,message)},onError:error=>{if(generation===mpfbGeneration)patientNotice('failed','The detailed patient could not load. The encounter controls remain available; retry the 3D patient when ready. '+String(error?.message||error));}});}catch(error){patientNotice('failed','Patient assets could not initialize. The encounter controls remain available. '+String(error?.message||error));return;}
 mpfbPatient=current;current.update(publicState);
 current.ready.then(ok=>{if(mpfbPatient!==current)return;send({type:'pcm-patient-metrics',sessionId:publicState.sessionId,ok,metrics:current.metrics,capabilities:current.capabilities});patientNotice(ok?'ready':'failed',ok?'Patient ready.':mpfbMessage||'The detailed patient is unavailable. Use the encounter controls while the 3D patient is unavailable.');actualPose();if(publicState.phase==='encounter'&&wantsMPFB())desiredCamera=patientFraming();if(trialEntryWait){const pending=trialEntryWait;trialEntryWait=null;if(pending.sessionId===publicState.sessionId&&publicState.phase==='briefing')enterRoom(pending.cmd);}});
}

function patientFraming(preset=cameraPreset,posture=publicState.posture){
 if(preset==='room')preset='full';
 const active=currentPatient(),anchors=active?.visible?active.anchors:null;
 if(anchors?.face)return conversationFrame(anchors.face,anchors.lap||anchors.abdomen,preset,posture);
 const faceHeight=publicState.appearance?.presentation==='female'?1.98:1.97;
 return conversationFrame(['supine','prone'].includes(posture)?V(0,1.48,-1.10):V(0,faceHeight,0),['supine','prone'].includes(posture)?V(0,1.34,.12):V(0,1.12,.17),preset,posture);
}
// Conservative world-space clearance snapshots, refreshed on a new pose/asset.
// Imported skin bounds include the current skeleton and morphs. A margin covers
// breathing and small idle motion; no clinical evidence is inferred from them.
let orbitClearanceCache=null;
function orbitClearances(){
 const patient=currentPatient(),key=[publicState.sessionId,publicState.posture,mpfbGeneration,trialGeneration,patient?.loaded].join(':');
 if(orbitClearanceCache?.key===key)return orbitClearanceCache.value;
 const obstacles=[],boundaries=[];
 for(const mesh of scene.meshes){
  if(mesh.isDisposed()||!mesh.isEnabled()||!mesh.isVisible||!mesh.getTotalVertices()||/Action location|Technique|Reference stethoscope|Comparison guide|InteriorTest baked/i.test(mesh.name))continue;
  if(patient?.ownsMesh?.(mesh))mesh.refreshBoundingInfo(true,true);
  mesh.computeWorldMatrix(true);const bounds=mesh.getBoundingInfo().boundingBox;
  const box={min:bounds.minimumWorld.clone(),max:bounds.maximumWorld.clone()};
  if(/floor|ceiling/i.test(mesh.name))continue;
  if(/wall|door jamb|door lintel|hinged examination-room door/i.test(mesh.name))boundaries.push(box);else obstacles.push(box);
 }
 // Below a lying patient's support, the table hides the entire patient.
 // Keep that orbit above the support plane while retaining all azimuths.
 const floorY=['supine','prone'].includes(publicState.posture)?Math.max(.20,(patient?.anchors?.lap?.y||1.15)+.08):.20;
 if(scene.getMeshByName('InteriorTest baked clinical room'))boundaries.push({min:V(-6.06,0,-4.06),max:V(-5.94,7.5,8.8)},{min:V(5.94,0,-4.06),max:V(6.06,7.5,8.8)},{min:V(-6,0,-4.06),max:V(6,7.5,-3.94)});
 const value={obstacles,boundaries,floorY,ceilingY:7.25,minimum:.38,maximum:5.5,padding:.12};orbitClearanceCache={key,value};return value;
}
function framePatient(){const framing=patientFraming();view(framing.position,framing.target,framing.fov);}
function wantsTrial(){return false;}
function trialNotice(status,message){trialStatus=status;trialMessage=message||'';if(!wantsTrial())return;send({type:'pcm-trial-status',sessionId:publicState.sessionId,status,message:trialMessage});window.pcmTrialStatus?.({status,message:trialMessage});}
function ensureTrial(){
 if(!wantsTrial()||trialPatient||trialStatus==='failed')return;
 trialNotice('loading',publicState.phase==='briefing'?'Preparing the detailed trial patient. The encounter clock has not started.':'Preparing the detailed trial patient. Your encounter remains available.');
 const generation=++trialGeneration;let current;try{current=createTrialPatient(scene,{getLookTarget:()=>camera.position,shadowGenerator:shadowCaster,allowedCaseIds:['renal-colicky-flank'],onStatus:({state,message})=>{if(generation===trialGeneration)trialNotice(state,message)},onError:error=>{console.warn('PCM trial patient:',error?.message||String(error));if(generation===trialGeneration)trialNotice('failed','The trial patient could not load. The encounter controls remain available; retry the 3D patient when ready. '+String(error?.message||error))}});}catch(error){console.warn('PCM trial setup:',error);trialNotice('failed','The trial patient could not initialize. The encounter controls remain available. '+String(error?.message||error));return;}trialPatient=current;
 trialPatient.update(publicState);
 current.ready.then(ok=>{if(trialPatient!==current)return;send({type:'pcm-trial-metrics',sessionId:publicState.sessionId,ok,metrics:trialPatient.metrics,capabilities:trialPatient.capabilities});trialNotice(ok?'ready':'failed',ok?'Human Generator trial patient ready. Original watermarks retained.':(trialMessage||'The trial patient is unavailable. Use the encounter controls while the 3D patient is unavailable.'));actualPose();if(publicState.phase==='encounter')desiredCamera=patientFraming();if(trialEntryWait){const pending=trialEntryWait;trialEntryWait=null;if(pending.sessionId===publicState.sessionId&&publicState.phase==='briefing')enterRoom(pending.cmd);}});
}
const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,Number(v)||0));
function send(data){parent.postMessage({...data,renderer:'babylon'},location.origin)}
function mat(name,color){const m=new StandardMaterial(name,scene);m.diffuseColor=Color3.FromHexString(color);m.specularColor=new Color3(.15,.15,.15);return m}
function view(position,target=patientTarget,fov=.65){camera.setTarget(target);camera.setPosition(position);camera.fov=fov;navigation?.remember();}
function selectView(preset){if(publicState.phase!=='encounter'||entrance||lesson)return;cameraPreset=['face','full'].includes(preset)?preset:'patient';try{if(publicState.sessionId)localStorage.setItem('pcm-camera.'+publicState.sessionId,cameraPreset);}catch{}navigation?.setAdjusting(false);poseCameraUntil=0;desiredCamera=patientFraming(cameraPreset);window.pcmCameraPreset?.(cameraPreset);}
function actualPose(){
 clinicalTable?.update(publicState);
 trialPatient?.update(publicState);trialPatient?.setEnabled(wantsTrial());
 mpfbPatient?.update(publicState);mpfbPatient?.setEnabled(wantsMPFB());
 // The old block models are never a fallback. A failed modern asset leaves a
 // clear recovery notice while the encounter's accessible controls keep working.
}
function disposeTools(){for(const m of tools)m.dispose();tools=[]}
function line(points){const m=MeshBuilder.CreateLines('Technique comparison guide',{points},scene);m.color=Color3.FromHexString('#d29224');tools.push(m);return m}
function scope(point,posterior=false){const instrument=MeshBuilder.CreateCylinder('Reference stethoscope',{height:.018,diameter:.085,tessellation:20},scene);instrument.material=mat('Stethoscope','#486263');instrument.position=point;if(posterior)instrument.rotation.x=Math.PI/2;tools.push(instrument);line([point,point.add(V(.13,.09,.04)),point.add(V(.25,.1,.07))])}
function stopTechnique(){
 techniqueStudio?.stop();lesson=null;disposeTools();actualPose();
 if(savedCamera){view(savedCamera.position,savedCamera.target,savedCamera.fov);savedCamera=null;}
}
function showTechnique(cmd){
 navigation?.setAdjusting(false);if(!['guided','coached'].includes(publicState.mode)||publicState.phase!=='encounter')return;
 if(!savedCamera)savedCamera={position:camera.position.clone(),target:camera.target.clone(),fov:camera.fov};
 desiredCamera=null;poseCameraUntil=0;disposeTools();lesson=cmd.lesson;
 techniqueStudio ||= createTechniquePatient({scene,getPatient:()=>currentPatient(),getState:()=>publicState,
  setFrame:frame=>view(frame.position,frame.target,frame.fov),
  notice:message=>window.pcmTechniqueNotice?.(message),updateTable:s=>clinicalTable?.update(s)});
 if(!techniqueStudio.show(cmd)){lesson=null;actualPose();}
}
function applyState(s){const previous=publicState;publicState=s;if(s.sessionId!==previous.sessionId){try{const saved=localStorage.getItem('pcm-camera.'+s.sessionId);cameraPreset=['face','full','patient'].includes(saved)?saved:'patient';}catch{cameraPreset='patient';}window.pcmCameraPreset?.(cameraPreset);}ensureTrial();ensureMPFB();if(lesson&&(!['guided','coached'].includes(s.mode)||s.phase!=='encounter'))stopTechnique();if(!lesson)actualPose();if(s.patientReply&&s.patientReply!==reply){reply=s.patientReply;speechUntil=performance.now()+Math.min(6000,reply.length*29)}if(previous.sessionId!==s.sessionId&&previous.sessionId){stopTechnique();poseCameraUntil=0;entered=false;entrance=null;trialEntryWait=null;}if(s.phase==='briefing'&&!entered&&!entrance){doorPivot.rotation.y=0;doorSurround.setEnabled(true);view(outsideCamera,outsideTarget);navigation?.setAdjusting(false);}else if(s.phase==='encounter'&&!entrance&&!entered){entered=true;doorPivot.rotation.y=-1.64;doorSurround.setEnabled(false);framePatient();}if(s.phase==='encounter'&&!entrance){if(previous.posture!==s.posture){navigation?.setAdjusting(false);poseCameraFrom=previous.posture||'seated';poseCameraUntil=performance.now()+700;desiredCamera=null;}}if(s.phase==='encounter'&&(previous.visualDemo!==s.visualDemo||previous.appearance?.model!==s.appearance?.model||previous.comparePrevious!==s.comparePrevious))desiredCamera=patientFraming();if(s.phase!=='encounter'){navigation?.setAdjusting(false);disposeTools();}}
function resetEntry(){trialEntryWait=null;entrance=null;entered=false;desiredCamera=null;doorPivot.rotation.y=0;doorSurround.setEnabled(true);view(outsideCamera,outsideTarget);navigation?.setAdjusting(false);}
function physicalDoor(){doorSurround=new TransformNode('Doorway and corridor',scene);const wood=mat('Door oak','#b89469'),trim=mat('Door trim','#49645b'),wall=mat('Hallway plaster','#e8e8df');function box(name,position,size,material,parent=doorSurround){const m=MeshBuilder.CreateBox(name,{width:size.x,height:size.y,depth:size.z},scene);m.position=position;m.material=material;m.parent=parent;return m}box('Corridor floor',V(0,-.025,4.85),V(7,.045,4.6),mat('Hall floor','#d6d4c7'));for(const side of[-1,1]){box('Corridor wall',V(side*2.08,1.6,2.6),V(2.72,3.2,.13),wall);box('Door jamb',V(side*.74,1.39,2.6),V(.11,2.8,.19),trim);}box('Door lintel',V(0,2.79,2.6),V(1.59,.16,.2),trim);box('Wall above doorway',V(0,3.04,2.6),V(1.42,.34,.13),wall);doorPivot=new TransformNode('Working door hinge',scene);doorPivot.position=V(-.68,0,2.6);doorPivot.parent=doorSurround;box('Hinged examination-room door',V(.68,1.35,0),V(1.36,2.70,.075),wood,doorPivot);for(let i=0;i<12;i++)box('Fine door grain',V(.09+i*.102,1.34,.042),V(.004,2.48,.005),trim,doorPivot);const handle=box('Door lever',V(1.17,1.2,.103),V(.15,.035,.035),mat('Door handle','#d2b378'),doorPivot);box('Door lever backplate',V(1.22,1.20,.071),V(.06,.18,.025),handle.material,doorPivot);}
function enterRoom(cmd){if(entrance&&cmd.requestId===entrance.id&&cmd.skip){finishEntrance();return;}if((wantsTrial()&&trialStatus==='loading')||(wantsMPFB()&&mpfbStatus==='loading')){trialEntryWait={cmd,sessionId:publicState.sessionId};return;}if(publicState.phase!=='briefing'||!publicState.sessionId||entrance||entered||typeof cmd.requestId!=='string')return;stopTechnique();desiredCamera=null;navigation?.setAdjusting(false);entrance={id:cmd.requestId,start:performance.now(),skip:cmd.skip||publicState.reducedMotion};if(entrance.skip)finishEntrance();}
function finishEntrance(){if(!entrance)return;const id=entrance.id;entrance=null;entered=true;doorPivot.rotation.y=-1.64;doorSurround.setEnabled(false);framePatient();send({type:'pcm-room-entered',requestId:id,sessionId:publicState.sessionId});}
function animateEntrance(now){if(!entrance)return;if(publicState.reducedMotion){finishEntrance();return;}const u=clamp((now-entrance.start)/1900),s=x=>x*x*(3-2*x);doorPivot.rotation.y=-1.64*s(clamp(u/.40));const walk=s(clamp((u-.25)/.75));const finish=patientFraming();view(Vector3.Lerp(outsideCamera,finish.position,walk),Vector3.Lerp(outsideTarget,finish.target,walk));if(u>=1)finishEntrance();}
function regionFocus(region){if(lesson)return;navigation?.setAdjusting(false);const active=currentPatient(),marks=active?.visible?active.anchors:null;if(marks?.face){const target=region==='HEENT'?marks.face:region==='Abdomen'?marks.abdomen:region==='MSK'?marks.lap:marks.chest||marks.patient;if(target){desiredCamera={target,position:target.add(['supine','prone'].includes(publicState.posture)?V(1.0,1.50,.50):region==='HEENT'?V(.07,0,.67):V(.38,.22,1.70))};return;}}const targets={HEENT:V(0,2,0),Heart:V(0,1.6,0),Lungs:V(0,1.55,0),Abdomen:V(0,1.2,['supine','prone'].includes(publicState.posture)?-.4:0),Neurologic:V(0,1.8,0),MSK:V(0,.9,.2),General:patientTarget};desiredCamera={position:region==='HEENT'?V(.24,2.08,1.18):V(.44,1.96,2.52),target:targets[region]||patientTarget}}
function showExam(cmd){if(lesson)return;currentPatient()?.examine(cmd);disposeTools();const points={Heart:V(-.1,1.58,.22),Lungs:V(.16,1.6,.22),Abdomen:['supine','prone'].includes(publicState.posture)?V(.1,1.44,-.38):V(.1,1.25,.23),Neurologic:V(.13,2.0,.19),HEENT:V(.13,2.0,.19),MSK:V(.2,.97,.7)};let point=points[cmd.region]||V(.1,1.5,.25);if(['supine','prone'].includes(publicState.posture)){if(['Heart','Lungs'].includes(cmd.region))point=V(.12,1.45,-.61);if(['HEENT','Neurologic'].includes(cmd.region))point=V(.07,1.48,-1.10);if(cmd.region==='MSK')point=V(.18,1.36,.38);}else if(cmd.region==='Lungs'&&cmd.components?.includes('posterior')){point=V(.15,1.60,-.20);desiredCamera={position:V(.75,1.96,-2.40),target:V(0,1.55,0)};}const active=currentPatient(),marks=active?.visible?active.anchors:null;if(marks){const anchor=['HEENT','Neurologic'].includes(cmd.region)?marks.face:cmd.region==='Abdomen'?marks.abdomen:cmd.region==='MSK'?marks.lap:marks.chest;if(anchor)point=anchor.add(['supine','prone'].includes(publicState.posture)?V(.08,.12,0):V(.08,0,.16));if(cmd.components?.includes('cva tenderness')&&marks.abdomen){point=marks.abdomen.add(V(.16,.05,-.22));desiredCamera={target:marks.abdomen,position:marks.abdomen.add(V(.85,.5,-2.25))};}}if(/auscultate/.test(cmd.maneuver_id||''))scope(point,cmd.region==='Heart'||cmd.region==='Lungs');else{const marker=MeshBuilder.CreateTorus('Action location — illustrative',{diameter:.13,thickness:.006,tessellation:30},scene);marker.position=point;marker.rotation.x=Math.PI/2;marker.material=mat('Action marker','#bb8745');tools.push(marker);}setTimeout(()=>{if(!lesson)disposeTools()},3000)}
async function boot(){engine=new Engine(canvas,true,{preserveDrawingBuffer:false,stencil:true,antialias:true});engine.setHardwareScalingLevel(1/Math.min(devicePixelRatio||1,1.5));scene=new Scene(engine);scene.useRightHandedSystem=true;scene.clearColor=new Color4(.88,.9,.86,1);scene.imageProcessingConfiguration.exposure=.90;scene.imageProcessingConfiguration.contrast=1.16;camera=new ArcRotateCamera('Room camera',0,0,3,patientTarget,scene);view(outsideCamera,outsideTarget);camera.inputs.clear();scene.preventDefaultOnPointerDown=false;scene.preventDefaultOnPointerUp=false;navigation=createCameraNavigation({canvas,camera,allowed:()=>publicState.phase==='encounter'&&!entrance&&!lesson&&!currentPatient()?.transition,constraints:orbitClearances,onChange:active=>window.pcmCameraAdjusting?.(active),onInteraction:()=>{desiredCamera=null;poseCameraUntil=0;}});navigation.remember();camera.fov=.65;camera.minZ=.055;
 const hemi=new HemisphericLight('Soft room light',V(0,1,0),scene);hemi.intensity=.64;hemi.groundColor=new Color3(.38,.34,.28);const sun=new DirectionalLight('Window light',V(.35,-.75,-.42),scene);sun.intensity=1.12;sun.diffuse=new Color3(1,.93,.85);sun.position=V(-2,4,3);const fill=new HemisphericLight('Portrait fill',V(0,.3,1),scene);fill.intensity=.16;physicalDoor();
 const imported=await SceneLoader.ImportMeshAsync('',new URL('../assets/',import.meta.url).href,'encounter-room.glb?v=room-clearance-1',scene,progress=>{if(progress.lengthComputable)document.getElementById('progress').value=progress.loaded/progress.total});for(const name of ['Male_SeatedRoot','Male_SupineRoot','Female_SeatedRoot','Female_SupineRoot'])scene.getTransformNodeByName(name)?.dispose(false,false);
 const shadow=new ShadowGenerator(1024,sun);shadowCaster=shadow;shadow.usePercentageCloserFiltering=true;shadow.filteringQuality=ShadowGenerator.QUALITY_MEDIUM;shadow.bias=.0003;shadow.normalBias=.0002;for(const m of imported.meshes){if(m.isDisposed())continue;m.receiveShadows=true;if(m.getTotalVertices()>0&&!/wall|floor|soffit|glazing|daylight|InteriorTest baked/i.test(m.name))shadow.addShadowCaster(m);}
 const environmentReport=await applyClinicalEnvironment(scene);
 if(engine.webGLVersion>1){try{const ao=new SSAO2RenderingPipeline('Clinic contact shadows',scene,{ssaoRatio:.5,blurRatio:.5},[camera]);ao.radius=.22;ao.totalStrength=.40;ao.samples=16;ao.expensiveBlur=true;ao.maxZ=12;environmentReport.contactShadows=true;}catch(e){environmentReport.contactShadows=false;}}
 if(location.hostname==='127.0.0.1')window.pcmRoomInspection=()=>({scene,camera,gesture:currentPatient()?.gesture,anchors:currentPatient()?.anchors,fps:engine.getFps()});
 try{clinicalTable=await createClinicalTable(scene,{shadowGenerator:shadow});clinicalTable.update(publicState);environmentReport.table=clinicalTable.report;}catch(error){console.warn('Clinical table fallback:',error);environmentReport.table={fallback:true,message:String(error)};}
 scene.onPointerObservable.add(info=>{if(info.type!==PointerEventTypes.POINTERPICK||navigation?.adjusting||lesson||publicState.phase!=='encounter')return;const mesh=info.pickInfo?.pickedMesh;const detailed=currentPatient();if(detailed?.ownsMesh(mesh)){const region=detailed.regionAt(info.pickInfo.pickedPoint,mesh,info.pickInfo);if(region)window.pcmUnityEmit({type:'pcm-unity-action',requestId:crypto.randomUUID(),sessionId:publicState.sessionId,action:'select_region',region});return;}return;});
 scene.onBeforeRenderObservable.add(()=>{const now=performance.now();animateEntrance(now);currentPatient()?.animate(now);techniqueStudio?.animate?.(now);const transition=currentPatient()?.transition;const cutting=transition?.kind==='reposition'&&!lesson;window.pcmPositionTransition?.(cutting?transition.progress:null);if(cutting){desiredCamera=null;if(transition.progress>=.5)framePatient();}if(!cutting&&poseCameraUntil&&now<=poseCameraUntil&&!lesson&&!entrance){const frame=transitionConversationFrame(patientFraming(cameraPreset,poseCameraFrom),patientFraming(),publicState.reducedMotion?1:1-(poseCameraUntil-now)/700);view(frame.position,frame.target,frame.fov);desiredCamera=null;}else if(!cutting&&poseCameraUntil){poseCameraUntil=0;desiredCamera=patientFraming();}if(desiredCamera&&!entrance&&!cutting&&!lesson){const p=Vector3.Lerp(camera.position,desiredCamera.position,publicState.reducedMotion?1:.12),target=Vector3.Lerp(camera.target,desiredCamera.target,publicState.reducedMotion?1:.12);view(p,target,camera.fov+((desiredCamera.fov||.65)-camera.fov)*(publicState.reducedMotion?1:.12));if(Vector3.Distance(p,desiredCamera.position)<.001&&Math.abs(camera.fov-(desiredCamera.fov||.65))<.001)desiredCamera=null;}if(headPivot&&headTarget)headPivot.rotationQuaternion=Quaternion.Slerp(headPivot.rotationQuaternion,headTarget,publicState.reducedMotion?1:.08)});
 let last=0;engine.runRenderLoop(()=>{const now=performance.now();if(now-last<24||document.hidden)return;last=now;scene.render()});new ResizeObserver(()=>engine.resize()).observe(canvas);window.addEventListener('pagehide',()=>engine.dispose(),{once:true});canvas.addEventListener('webglcontextlost',()=>send({type:'pcm-unity-error',message:'3D context interrupted; use the main encounter controls.'}));
 const adapter={SendMessage(_object,method,payload){try{if(method==='ApplyState')applyState(JSON.parse(payload));else if(method==='Acknowledge'){nodUntil=performance.now()+900;currentPatient()?.acknowledge();}else if(method==='ResetEntry')resetEntry();else if(method==='ReloadPatient'){if(wantsMPFB()){mpfbPatient?.dispose();mpfbPatient=null;mpfbStatus='idle';ensureMPFB();actualPose();}else{trialPatient?.dispose();trialPatient=null;trialStatus='idle';ensureTrial();actualPose();}}else if(method==='ReloadTrial'){trialPatient?.dispose();trialPatient=null;trialStatus='idle';ensureTrial();actualPose();}else if(method==='EnterRoom')enterRoom(JSON.parse(payload));else if(method==='FocusRegion')regionFocus(payload);else if(method==='SetView')selectView(payload);else if(method==='SetCameraAdjust')navigation?.setAdjusting(payload==='true');else if(method==='MoveCamera'){const moves={closer:[0,0,-.12],farther:[0,0,.12]};if(moves[payload])navigation?.move(...moves[payload]);}else if(method==='ShowExam')showExam(JSON.parse(payload));else if(method==='ShowTechnique')showTechnique(JSON.parse(payload));else if(method==='StopTechnique')stopTechnique()}catch(error){console.warn('PCM room action:',error);send({type:'pcm-unity-error',message:String(error)})}}};window.pcmBabylonReady(adapter);send({type:'pcm-room-metrics',loadMs:Math.round(performance.now()-started),rendererVersion:Engine.Version,meshCount:imported.meshes.length,patientPresentations:2,animation:'authored-four-postures',environment:environmentReport})}
boot().catch(error=>{document.getElementById('load').textContent='Patient room unavailable. Continue with the main encounter controls.';send({type:'pcm-unity-error',message:String(error)});console.error(error)});
