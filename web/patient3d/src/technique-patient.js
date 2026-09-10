/** In-place technique overlays for the current authored patient.
 * This controller never clones a model, calls an examination, changes the
 * encounter state, or writes evidence. Posture changes exist only in the view.
 */
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {Color3} from '@babylonjs/core/Maths/math.color.js';
import {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';

const V=(x,y,z)=>new Vector3(x,y,z);
const LESSONS=new Set(['lungs','abdomen','positional']);
const allowed=state=>state?.phase==='encounter'&&['guided','coached'].includes(state.mode);
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
export function techniqueVisualState(state,command) {
  if(!allowed(state)||!LESSONS.has(command?.lesson))return null;
  const step=clamp(Math.floor(Number(command.step)||0),0,3);
  return {...state,
    posture:command.lesson==='abdomen'||(command.lesson==='positional'&&step>=2)?'supine':'seated',
    // The figure demonstrates a process; it neither answers nor exhibits a
    // case-specific response during this separate, explicitly labeled lesson.
    speaking:false,listening:false,
    affect:{discomfort:0,concern:0,guardRegion:null},
    demeanor:{style:'calm',authored:false,tension:0,engagement:.65},
  };
}

/** All coordinates are derived from the active rig's world-space landmarks.
 * The guides are approximate teaching locations, not validated surface anatomy.
 */
export function techniqueGuideGeometry(anchors,command) {
  const {face,chest,abdomen,lap}=anchors||{};
  if(!face||!chest||!abdomen||!lap)return null;
  const step=clamp(Math.floor(Number(command.step)||0),0,3);
  if(command.lesson==='lungs'){
    const torsoHeight=clamp(face.y-lap.y,.54,.95);
    const halfWidth=torsoHeight*.20;
    const backZ=Math.min(chest.z,abdomen.z)-.27;
    const ys=[chest.y+torsoHeight*.10,chest.y-torsoHeight*.07,abdomen.y+torsoHeight*.025];
    const pairs=ys.flatMap(y=>[V(-halfWidth,y,backZ),V(halfWidth,y,backZ)]).map(p=>p.add(V(chest.x,0,0)));
    const index=[0,1,2,4][step];
    return {paths:[pairs],point:pairs[index],posterior:true,
      frame:{target:Vector3.Lerp(chest,abdomen,.20),position:chest.add(V(.64,.30,-1.95)),fov:.64}};
  }
  if(command.lesson==='abdomen'){
    const axis=chest.subtract(lap);axis.y=0;axis.normalize();
    const center=abdomen.add(V(0,.06,0)),cross=V(1,0,0),a=.135,b=.115;
    const corner=(x,z)=>center.add(cross.scale(x*a)).add(axis.scale(z*b));
    const corners=[corner(-1,-1),corner(1,-1),corner(1,1),corner(-1,1)];
    return {paths:[[...corners,corners[0]],[corner(-1,0),corner(1,0)],[corner(0,-1),corner(0,1)]],point:center.add(cross.scale(.085)),posterior:false,
      frame:{target:abdomen,position:abdomen.add(V(1.0,1.35,.65)),fov:.66}};
  }
  const supine=step>=2;
  const center=face.add(V(0,.13,0));
  const angle=step===0?0:(step===3?-1:1)*Math.PI/4;
  const arc=[];for(let i=0;i<=16;i++){const t=angle*i/16;arc.push(center.add(V(Math.sin(t)*.19,0,Math.cos(t)*.19)));}
  const supportCenter=face.add(V(0,-.13,supine?.03:-.035));
  const support=[supportCenter.add(V(-.17,.025,0)),supportCenter,supportCenter.add(V(.17,.025,0))];
  const paths=step===0?[[center,center.add(V(0,0,.19))]]:[[center,center.add(V(0,0,.19))],arc,[center,arc.at(-1)]];
  if(supine)paths.push(support);
  return {paths,point:null,posterior:false,
    frame:{target:face.add(V(0,-.045,0)),position:face.add(supine?V(.76,.77,-.42):V(.43,.18,1.18)),fov:.64}};
}

export function createTechniquePatient({scene,getPatient,getState,setFrame,notice,updateTable}) {
  let command=null,activePatient=null,stateRef=null,guide=null,marker=null;
  let lastGeometry=null,materials=[];
  const tracked=[];
  const lineColor=Color3.FromHexString('#c18b2e');
  function cleanup(){for(const mesh of tracked)mesh.dispose();tracked.length=0;for(const mat of materials)mat.dispose();materials=[];guide=null;marker=null;lastGeometry=null;}
  function material(name,color){const mat=new StandardMaterial(name,scene);mat.diffuseColor=Color3.FromHexString(color);mat.emissiveColor=mat.diffuseColor.scale(.18);mat.specularColor=Color3.Black();materials.push(mat);return mat;}
  function register(mesh){mesh.isPickable=false;mesh.metadata={pcmTechniqueGuide:true,noClinicalEvidence:true};tracked.push(mesh);return mesh;}
  function draw(geometry){
    if(!geometry)return;
    if(!guide){guide=register(MeshBuilder.CreateLineSystem('Technique guide — approximate locations',{lines:geometry.paths,updatable:true},scene));guide.color=lineColor;guide.renderingGroupId=1;}
    else MeshBuilder.CreateLineSystem(null,{lines:geometry.paths,instance:guide});
    if(geometry.point){
      if(!marker){
        if(command.lesson==='lungs'||(command.lesson==='abdomen'&&command.step===1)){
          marker=register(MeshBuilder.CreateCylinder('Illustrative stethoscope placement',{height:.018,diameter:.065,tessellation:24},scene));marker.material=material('Technique stethoscope','#2c6862');
        }else{
          marker=register(MeshBuilder.CreateTorus(command.step===2?'Percussion location guide':'Gentle palpation location guide',{diameter:.085,thickness:.007,tessellation:32},scene));marker.material=material('Technique placement guide','#c18b2e');
        }
        marker.renderingGroupId=1;
      }
      marker.position.copyFrom(geometry.point);marker.rotation.x=geometry.posterior?Math.PI/2:0;
      marker.setEnabled(command.lesson==='lungs'||command.step>0);
    }
    // Keep the camera attached to the same modern patient while its authored
    // seated/supine blend settles, including reduced-motion instant changes.
    setFrame?.(geometry.frame);
    lastGeometry=geometry;
  }
  function synchronize(){
    const state=getState(),patient=getPatient();
    if(!command||!allowed(state)||!patient?.loaded)return false;
    if(state!==stateRef||patient!==activePatient){
      const visual=techniqueVisualState(state,command);
      patient.update(visual);patient.setEnabled(true);updateTable?.(visual);
      activePatient=patient;stateRef=state;
    }
    return true;
  }
  return {
    get active(){return command!==null;},
    get command(){return command&&{...command};},
    get guideGeometry(){return lastGeometry;},
    show(next){
      const state=getState(),patient=getPatient();
      if(!allowed(state)||!LESSONS.has(next?.lesson))return false;
      if(!patient?.loaded||!patient.anchors){notice?.('The current patient is still loading. Close the lesson and try again when the patient is ready.');return false;}
      cleanup();command={lesson:next.lesson,step:clamp(Math.floor(Number(next.step)||0),0,3)};stateRef=null;
      synchronize();draw(techniqueGuideGeometry(patient.anchors,command));return true;
    },
    animate(){
      if(!command)return;
      if(!synchronize()){this.stop();return;}
      draw(techniqueGuideGeometry(activePatient.anchors,command));
    },
    stop(){
      if(!command)return;
      cleanup();command=null;stateRef=null;
      // Read the latest canonical state, rather than a stale captured posture or
      // wardrobe, so interruption, refresh and a view toggle cannot be undone.
      const state=getState();activePatient?.update(state);activePatient?.setEnabled(true);updateTable?.(state);activePatient=null;
    },
    dispose(){this.stop();cleanup();},
  };
}
