import assert from 'node:assert/strict';
import {createCameraNavigation,orbitDirection,rayBoxInterval,safeOrbitRadius} from '../src/camera-navigation.js';
import {conversationFrame} from '../src/patient-framing.js';
import {NullEngine} from '../node_modules/@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '../node_modules/@babylonjs/core/scene.js';
import {ArcRotateCamera} from '../node_modules/@babylonjs/core/Cameras/arcRotateCamera.js';
import {Vector3} from '../node_modules/@babylonjs/core/Maths/math.vector.js';
const engine=new NullEngine(),scene=new Scene(engine),V=(x,y,z)=>new Vector3(x,y,z),camera=new ArcRotateCamera('test',1.5,1.4,1.12,V(0,1.5,0),scene);
const handlers=new Map(),classes=new Set();let phaseAllowed=true,interactions=0,captured=null;
const canvas={classList:{toggle(n,v){v?classes.add(n):classes.delete(n)}},addEventListener(t,f){handlers.set(t,f)},removeEventListener(t){handlers.delete(t)},setPointerCapture(id){captured=id},hasPointerCapture(id){return id===captured},releasePointerCapture(){captured=null}};
let limits={};const nav=createCameraNavigation({canvas,camera,allowed:()=>phaseAllowed,constraints:()=>limits,onInteraction:()=>interactions++});nav.remember();
assert.deepEqual([...handlers.keys()].sort(),['lostpointercapture','pointercancel','pointerdown','pointermove','pointerup'].sort());
const event=(x={})=>({pointerType:'mouse',button:0,pointerId:1,clientX:100,clientY:100,preventDefault(){throw Error('Native browser defaults must remain available')},...x});
// Orbiting is always available inside the encounter: the separate "Adjust
// view" mode was removed, so a plain drag moves the camera with no mode to
// enter first. What must still be refused is a drag while the phase disallows
// it -- that is the real boundary.
phaseAllowed=false;
handlers.get('pointerdown')(event());handlers.get('pointermove')(event({clientX:140}));
assert.equal(interactions,0,'the camera moved while the phase disallowed it');
assert.equal(nav.move(.1,0,0),false,'move() succeeded while the phase disallowed it');
phaseAllowed=true;
handlers.get('pointerdown')(event());handlers.get('pointermove')(event({clientX:140}));
assert.equal(interactions,1,'a plain drag no longer orbits the camera');
handlers.get('pointerup')(event());interactions=0;
nav.setAdjusting(true);const baseline=interactions;
for(const modifier of ['ctrlKey','metaKey','altKey']){handlers.get('pointerdown')(event({[modifier]:true}));handlers.get('pointermove')(event({clientX:130}));assert.equal(interactions,baseline)}
handlers.get('pointerdown')(event({pointerType:'touch'}));handlers.get('pointermove')(event({pointerType:'touch',clientX:120}));assert.equal(interactions,baseline);
handlers.get('pointerdown')(event());handlers.get('pointermove')(event({clientX:130,clientY:120}));assert.equal(interactions,baseline+1);assert.notEqual(camera.alpha,1.5);handlers.get('pointerup')(event());assert.equal(captured,null);
// A phase/mode change or cancellation releases a live pointer capture.
handlers.get('pointerdown')(event());nav.setAdjusting(false);assert.equal(captured,null);
nav.setAdjusting(true);handlers.get('pointerdown')(event());handlers.get('pointercancel')(event());assert.equal(captured,null);
handlers.get('pointerdown')(event());handlers.get('pointermove')(event({ctrlKey:true}));assert.equal(captured,null);
// Crossing the numeric wrap is continuous and permits repeated full turns.
camera.alpha=2*Math.PI-.02;nav.move(.04,0,0);assert.ok(Math.abs(camera.alpha-(2*Math.PI+.02))<1e-9);
const from=camera.alpha;for(let i=0;i<360;i++)assert.equal(nav.move(Math.PI/60,0,0),true);assert.ok(Math.abs(camera.alpha-from-6*Math.PI)<1e-9);
const box=(min,max)=>({min,max});
limits={floorY:.20,ceilingY:3.05,boundaries:[box(V(-3.1,0,-3),V(-3,3.2,3)),box(V(3,0,-3),V(3.1,3.2,3)),box(V(-3,0,-3.1),V(3,3.2,-3)),box(V(-3,0,3),V(3,3.2,3.1))]};
const table=box(V(-.56,.1,-1.2),V(.56,1.09,1.1));
const profiles=[
 ['seated',V(0,1.95,.05),V(0,1.12,.17),box(V(-.42,.12,-.4),V(.42,2.05,.8))],
 ['supine',V(0,1.30,-.8),V(0,1.12,.15),box(V(-.4,1.02,-1.01),V(.4,1.49,.85))],
 ['standing',V(1.2,1.75,.2),V(1.2,.95,.2),box(V(.82,.02,-.1),V(1.58,1.88,.45))],
 ['prone',V(-.06,1.21,-.78),V(0,1.10,.13),box(V(-.41,1.02,-1.03),V(.41,1.42,.88))]
];
function verifyClear(label){camera.getViewMatrix(true);const pos=camera.position;assert.ok(pos.y>=limits.floorY-1e-8,label+' floor/support');assert.ok(pos.y<=3.05+1e-8,label+' ceiling');const dir=orbitDirection(camera.alpha,camera.beta);for(const obstacle of limits.obstacles){const hit=rayBoxInterval(camera.target,dir,obstacle,.12);assert.ok(!hit||camera.radius<hit[0]||camera.radius>hit[1],label+' body/table clearance')}for(const boundary of limits.boundaries){const hit=rayBoxInterval(camera.target,dir,boundary,.12);assert.ok(!hit||camera.radius<hit[0],label+' wall clearance')}}
for(const [posture,face,lap,body]of profiles){limits.obstacles=[body,table];limits.floorY=['supine','prone'].includes(posture)?lap.y+.08:.20;for(const preset of ['face','patient','full']){const f=conversationFrame(face,lap,preset,posture);camera.setTarget(f.target);camera.setPosition(f.position);nav.remember();assert.equal(nav.move(0,0,0),true);const initial=camera.alpha;
 for(let i=0;i<144;i++){assert.equal(nav.move(Math.PI/36,Math.sin(i/12)*.025,(i%12<6?-.03:.03)),true,posture);verifyClear(posture+' '+preset)}assert.ok(Math.abs(camera.alpha-initial-4*Math.PI)<1e-7,posture+' full orbit');
 for(let i=0;i<100;i++){assert.equal(nav.move(.08,.05,-.05),true);verifyClear(posture+' low angle')}
 for(let i=0;i<100;i++){assert.equal(nav.move(-.08,-.05,.05),true);verifyClear(posture+' high angle')}
 }}
// No giant jump through a wall or malformed numeric request.
assert.equal(nav.move(NaN,0,0),false);phaseAllowed=false;const before=[camera.alpha,camera.beta,camera.radius];assert.equal(nav.setAdjusting(true),false);assert.equal(nav.move(1,1,1),false);assert.deepEqual([camera.alpha,camera.beta,camera.radius],before);
nav.dispose();assert.equal(handlers.size,0);engine.dispose();console.log('Full 360 orbit, wrap continuity, all posture/preset clearance sweeps, native gestures and capture cleanup passed.');
