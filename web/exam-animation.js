/* Authored examination playback. This renderer knows technique only: no case
   findings, scoring, or normal/abnormal responses. The engine owns completion. */
(() => {
'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp=n=>Math.max(0,Math.min(1,n)),mix=(a,b,t)=>a+(b-a)*t;
const ease=t=>t*t*(3-2*t);
const path=d=>`<path d="${d}"/>`,line=(x1,y1,x2,y2,cls='')=>`<line class="${cls}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
const circle=(x,y,r,cls='')=>`<circle class="${cls}" cx="${x}" cy="${y}" r="${r}"/>`;
const txt=(x,y,t)=>`<text x="${x}" y="${y}" text-anchor="middle">${esc(t)}</text>`;
const ellipse=(x,y,rx,ry)=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}"/>`;
const torso=path('M38 9 L38 15 Q25 15 19 30 L27 37 L29 83 Q50 91 71 83 L73 37 L81 30 Q75 15 62 15 L62 9')+path('M32 25 Q41 27 50 24 Q59 27 68 25 M50 25 L50 57 M32 55 Q39 56 50 65 Q61 56 68 55');
const face=ellipse(50,43,24,30)+path('M26 37 Q19 33 23 48 L28 51 M74 37 Q81 33 77 48 L72 51 M40 71 L37 85 L22 93 M60 71 L63 85 L78 93')+path('M33 40 Q40 35 47 40 Q40 45 33 40 M53 40 Q60 35 67 40 Q60 45 53 40 M50 43 L47 54 L53 54 M40 62 Q50 67 60 62')+circle(40,40,2)+circle(60,40,2);
// Dedicated joint views keep the fixed segment fixed and make the motion plane explicit.
function jointMotion(st,u,focus){
 const t=Math.sin(Math.PI*u),m=st.motion||'',part=m.split('-').at(-1),op=u*4,opIndex=Math.min(3,Math.floor(op)),opTurn=Math.sin(Math.PI*(op-opIndex));let art='',caption='';
 if(focus==='hand'){
  art=path('M33 86 L34 56 Q50 49 66 56 L67 86Z');
  for(let i=0;i<4;i++){const x=37+i*8,spread=part==='side'?(i-1.5)*6*t:0,f=part==='flex'?t:part==='extend'?1-t:part==='rotate'&&i===opIndex?opTurn*2/3:0;
   art+=line(x,58,x+spread,36+13*f,'limb')+line(x+spread,36+13*f,x+spread+5*f,20+33*f,'limb')+circle(x,58,2);}
  if(part==='rotate'){const mx=mix(25,34,opTurn),tx=mix(20,37+opIndex*8+10/3,opTurn);art+=line(34,68,mx,52,'limb')+line(mx,52,tx,42,'limb');}else art+=line(34,68,25,52,'limb')+line(25,52,20,42,'limb');
  caption={flex:'Make a fist, then release',extend:'Straighten the fingers, then relax',side:'Spread fingers, then bring them together',rotate:'Touch thumb to fingertips; compare hands'}[part];
 }else if(focus==='torso'){
  if(part==='side'){art=rig({...st,view:'body',motion:'arm-abduct',activeROM:true},u);caption='Raise arms out to the sides as far as comfortable, then lower';}
  else if(part==='rotate'){art=path('M32 15 H68 V60 H32Z')+line(32,27,29,57,'limb')+line(68,27,71,57,'limb')+line(29,57,29-20*t,48,'limb')+line(71,57,71+20*t,48,'limb');caption='Elbows at sides: rotate forearms outward and inward';}
  else {const angle=part==='extend'?-0.65*t:2.8*t;const ex=45+25*Math.sin(angle),ey=42+18*Math.cos(angle),hx=45+35*Math.sin(angle),hy=42+35*Math.cos(angle);
   art=ellipse(43,17,7,9)+line(43,28,43,64,'limb')+line(43,64,34,88,'limb')+line(43,64,54,88,'limb')+line(45,42,ex,ey,'limb')+line(ex,ey,hx,hy,'limb');caption=part==='extend'?'Side view: move arm backward, then return':'Side view: raise arm forward, then lower';}
 }else if(focus==='joint'){
  const f=['flex','side'].includes(part)?t:1-t,k=[49,45],angle=.15+1.5*f;
  art=line(18,49,43,49,'table')+line(24,49,24,88,'table')+line(20,43,...k,'limb')+line(...k,49+32*Math.cos(angle),45+32*Math.sin(angle),'limb')+circle(...k,5);
  caption=(['side','rotate'].includes(part)?'Opposite knee: ':'Knee: ')+(['flex','side'].includes(part)?'bend and return':'straighten and relax');
 }else{
  const a=(part==='extend'?-.2:part==='rotate'?.15:part==='side'?.28:.5)*(part==='side'||part==='rotate'?Math.sin(2*Math.PI*u):t),hip=[50,66],top=[50+37*Math.sin(a),66-37*Math.cos(a)];
  art=line(43,66,40,91,'limb')+line(57,66,60,91,'limb')+line(42,66,58,66,'limb')+line(...hip,...top,'limb')+ellipse(top[0]+4*Math.sin(a),top[1]-11,7,9)+line(top[0]-4,top[1]+5,top[0]-10,top[1]+26,'limb')+line(top[0]+4,top[1]+5,top[0]+10,top[1]+26,'limb');
  if(part==='rotate'){const turn=.55*Math.sin(2*Math.PI*u),left=[50-17*Math.cos(turn),30+8*Math.sin(turn)],right=[50+17*Math.cos(turn),30-8*Math.sin(turn)];art=path(`M${left[0]} ${left[1]} Q50 21 ${right[0]} ${right[1]} L57 66 H43Z`)+ellipse(50,13,7,9)+line(...left,left[0]-4,left[1]+24,'limb')+line(...right,right[0]+4,right[1]+24,'limb')+line(43,66,40,91,'limb')+line(57,66,60,91,'limb')+path(`M${50+5*Math.sin(turn)} 29 Q${50+10*Math.sin(turn)} 48 50 65`);}
  caption={flex:'Side view: bend forward at hips and spine, then return',extend:'Side view: gently extend, then return',side:'Front view: bend to each side within comfort',rotate:'Pelvis still: gently turn the upper trunk each way'}[part];
 }
 return {art:`<g class="patient">${art}</g>`,caption};
}
function rig(stage,u){
 const m=stage.motion||'',v=stage.view;const t=Math.sin(Math.PI*u),wave=Math.sin(2*Math.PI*u*(m==='walk'||m==='walk-return'?6:1));
 // Motion variables are anatomically separate joints, not a whole-body wobble.
 let hip=[45,57],knee=[69,57],ankle=[88,57],head=[18,49],shoulder=[28,56];
 if(m==='slr-seated'||m==='knee'){
  const a=Math.PI/2*(1-t),k=[62,42],foot=[62+25*Math.cos(a),42+25*Math.sin(a)];
  let art=line(16,50,47,50,'table')+line(24,50,24,91,'table');
  art+=`<g class="patient">${ellipse(35,13,6,8)}${line(37,25,41,43,'limb')}${line(41,43,63,46,'limb rear')}${line(63,46,63,74,'limb rear')}${line(41,43,...k,'limb')}${line(...k,...foot,'limb')}${line(...foot,foot[0]+5,foot[1]-2,'limb')}${line(34,28,29,44,'limb')}</g>`;
  art+=hand(60,44,0,'palm')+hand(foot[0]-2,foot[1]+2,0,'palm');
  if(m==='knee')art+=arrow(foot[0],foot[1]-13,foot[0],foot[1]-3);
  return art+txt(48,94,m==='knee'?'Stabilize thigh · resist distal leg':'Hip stays flexed · extend the knee');
 }
 if(m==='obturator'){
  const ankle=[50-20*t,72];
  return `<g class="patient">${path('M37 12 H63 L61 31 H39Z')}${line(50,27,50,41,'limb')}${circle(50,41,6)}${line(50,41,...ankle,'limb')}${line(...ankle,ankle[0]-5,ankle[1]+2,'limb')}</g>${hand(50,42,0,'palm')}${hand(...ankle,0,'palm')}${arrow(49,81,30,81)}${txt(50,94,'End view · ankle out, hip rotates inward')}`;
 }
 if(v==='leg'||v==='supine'){
  if(m==='hip-flex'||m==='hip-resist'||m==='obturator'||m==='kernig'){
   const f=m==='hip-flex'?ease(clamp(u*1.4)):1;knee=[mix(69,45,f),mix(57,30,f)];ankle=[mix(88,68,f),mix(57,30,f)];
   if(m==='kernig')ankle=[45+23*Math.cos(-t*1.1),30+23*Math.sin(-t*1.1)];
   if(m==='obturator')ankle=[68+12*t,30+5*t];
  }
  if(m.startsWith('slr')){if(m.includes('seated')){hip=[42,38];knee=[66,38];ankle=[66+22*t,60-22*t];shoulder=[27,22];head=[20,14];}else{knee=[45+24*Math.cos(t),57-24*Math.sin(t)];ankle=[45+44*Math.cos(t),57-44*Math.sin(t)];}}
  if(m==='knee'){knee=[65,38];ankle=[65+21*t,59-21*t];}
  if(m==='neck-passive'||m==='neck-hold'){const f=m==='neck-hold'?1:t;head=[18+5*f,49-12*f];}
  if(m.startsWith('dix-')){const f=m==='dix-lower'?ease(clamp(u*2)):m==='dix-return'?1-ease(u):1;head=[mix(35,14,f),mix(12,60,f)];shoulder=[mix(40,27,f),mix(25,54,f)];}
  let s=line(m.startsWith('dix-')?27:14,66,92,66,'table')+line(27,66,27,91,'table')+line(83,66,83,91,'table');
  s+=`<g class="patient">${line(...shoulder,...hip,'limb')}${line(...hip,70,61,'limb rear')}${line(70,61,88,61,'limb rear')}${line(...hip,...knee,'limb')}${line(...knee,...ankle,'limb')}${line(ankle[0],ankle[1],ankle[0]+5,ankle[1]-3,'limb')}${line(...shoulder,30,61,'limb')}${line(30,61,42,62,'limb')}${line(head[0]+5,head[1]+3,...shoulder,'limb')}${ellipse(...head,6,8)}</g>`;
  if(m==='hip-flex'||m==='kernig'||m==='obturator'||m.startsWith('slr'))s+=hand(...ankle,0)+hand(...knee,0);
  if(m.startsWith('neck-'))s+=hand(head[0]-4,head[1]+4,0)+hand(...shoulder,0,'palm');
  if(m.startsWith('dix-'))s+=hand(head[0]-5,head[1]+3,0)+hand(head[0]+5,head[1]+3,0);
  if(m.startsWith('dix-'))s+=txt(58,94,'Head supported beyond table edge');
  if(m==='obturator')s+=txt(65,78,'ankle outward → hip inward');
  if(m==='hip-resist'||m==='knee')s+=hand(...knee,0)+arrow(knee[0],knee[1]-12,knee[0],knee[1]-2);
  return s;
 }
 let lx=40,rx=60,ly=85,ry=85,la=[27,56],ra=[73,56],hn=[50,16];
 if(m==='walk'||m==='walk-return'){lx+=10*wave;rx-=10*wave;ly-=5*Math.max(0,wave);ry+=5*Math.min(0,wave);la=[27+6*wave,56];ra=[73-6*wave,56];}
 if(['arms-forward','finger-nose','arm-abduct','shrug'].includes(m)){la=[mix(28,5,t),mix(54,32,t)];ra=[mix(72,95,t),mix(54,32,t)];if(m==='arms-forward'){la=[36,48];ra=[64,48];}if(m==='finger-nose'){la=[mix(21,48,t),mix(36,20,t)];ra=[79,36];}if(m==='shrug'){la=[28,52-6*t];ra=[72,52-6*t];}}
 if(m==='arm-abduct'&&stage.activeROM){const a=2.9*t;la=[34-35*Math.sin(a),31+35*Math.cos(a)];ra=[66+35*Math.sin(a),31+35*Math.cos(a)];}
 if(m==='feet-together'||m==='eyes-closed'){lx=47;rx=53;}
 if(m==='bp-standing')la=[22,45];
 if(m==='arms-forward')return `<g class="patient">${ellipse(31,22,7,9)}${line(32,32,36,72,'limb')}${line(34,38,72,38,'limb')}${line(36,42,74,42,'limb rear')}${ellipse(77,37,5,2)}${ellipse(78,42,5,2)}${line(36,72,57,72,'limb')}${line(57,72,57,93,'limb')}</g>${txt(52,13,'Side view · arms forward, palms up')}`;
 let art=`<g class="patient">${ellipse(...hn,7,9)}${path('M43 25 Q32 29 33 40 L38 59 Q50 63 62 59 L67 40 Q68 29 57 25Z')}${line(34,31,...la,'limb')}${line(66,31,...ra,'limb')}${line(42,61,lx,ly,'limb')}${line(58,61,rx,ry,'limb')}${line(lx,ly,lx-4,ly+3,'limb')}${line(rx,ry,rx+4,ry+3,'limb')}</g>`+(m==='eyes-closed'?path('M46 16 h3 M51 16 h3'):path('M46 16 h1 M53 16 h1'))+(m==='finger-nose'?circle(20,34,2,'target'):'' )+(m==='arm-abduct'&&!stage.activeROM?hand(...la,0)+hand(...ra,0):m==='shrug'?hand(34,29-2*t,0,'palm')+hand(66,29-2*t,0,'palm'):'');
 if(m==='feet-together'||m==='eyes-closed')art+=hand(80,40,0,'palm')+txt(81,65,'Guard nearby');
 if(m==='walk'||m==='walk-return'){const z=m==='walk'?1-.35*u:.65+.35*u;art=`<g transform="translate(${50*(1-z)} ${12*(1-z)}) scale(${z})">${art}</g>`+txt(50,99,m==='walk'?'Walk away · observe from behind':'Turn comfortably, then walk back');}
 if(m==='bp-standing')art+=`<g class="patient">${line(22,45,9,35,'limb')}</g>`+line(4,41,22,48,'table');
 return art;
}
function body(st,u,focus){
 let v=st.view,m=st.motion||'',t=Math.sin(Math.PI*u);
 if(v==='region'&&m.startsWith('region-'))return jointMotion(st,u,focus||'back').art;
 if(v==='region')v=focus||'back';
 let b='';
 if(m==='elbow-resist'||m==='wrist-resist'||m==='ankle-resist'){
  const elbow=m==='elbow-resist',ank=m==='ankle-resist',pivot=ank?[46,65]:elbow?[50,55]:[60,48];
  const a=ank?-.45+.9*t:elbow?-1.4*t:-.55+1.1*t,tip=[pivot[0]+(elbow?28:22)*Math.cos(a),pivot[1]+(elbow?28:22)*Math.sin(a)];
  b=ank?line(46,17,...pivot,'limb'):line(elbow?25:17,elbow?23:48,...pivot,'limb');
  b+=line(...pivot,...tip,'limb')+circle(...pivot,3);
  return `<g class="patient">${b}</g>${hand(pivot[0]-8,pivot[1]+3,0,'palm')}${hand(...tip,0,'palm')}${arrow(tip[0],tip[1]-14,tip[0],tip[1]-4)}${txt(50,94,ank?'Side view · ankle up and down':elbow?'Stabilize upper arm · bend and straighten elbow':'Side view · forearm still, extend wrist')}`;
 }
 if(m==='grip')return `<g class="patient">${path('M35 85 L33 54 Q40 38 63 46 L69 69 L62 85Z')}${path(`M35 52 Q50 ${35+13*t} 64 52 M36 59 Q50 ${42+13*t} 66 59 M38 66 Q51 ${49+13*t} 65 66`)}</g><g class="examiner-hand">${path('M52 91 L52 45 Q52 42 55 43 L56 72 L59 45 Q61 42 63 45 L64 91Z')}</g>${txt(50,20,'Squeeze examiner’s two fingers; compare sides')}`;
 if(v==='torso'||v==='back'){b=torso;if(v==='back')b+=path('M50 17 V79 M36 30 Q28 42 41 48 M64 30 Q72 42 59 48');else b+=path('M32 31 Q40 36 46 32 M54 32 Q60 36 68 31');}
 else if(v==='abdomen'){b=path('M34 12 Q50 18 66 12 L74 29 L73 73 Q50 86 27 73 L26 29 Z')+path('M30 27 Q38 31 50 23 Q62 31 70 27')+circle(50,51,1)+line(50,24,50,74,'guide')+line(27,51,73,51,'guide');if(m==='roll'||m==='side')b=`<g transform="translate(${m==='roll'?t*12:12} 0) scale(.8 1)">${b}</g>`;}
 else if(v==='head'){b=face;if(m==='neck-turn'||m==='dix-turn')b=`<g transform="translate(${12*t} 0) scale(${1-.15*t} 1)">${b}</g>`;if(m==='neck-turn'||m==='dix-turn')b+=txt(50,8,'Head turn · keep shoulders still');if(m==='face-upper')b+=path(`M34 ${32-3*t} Q40 ${29-3*t} 46 ${32-3*t} M54 ${32-3*t} Q60 ${29-3*t} 66 ${32-3*t}`);if(m==='face-eyes')b+=`<g fill="#efe1cd" stroke="none">${ellipse(40,40,8,5)}${ellipse(60,40,8,5)}</g>`+path('M33 40 Q40 43 47 40 M53 40 Q60 43 67 40');
 if(m==='face-smile')b+=`<path fill="#f8faf4" d="M${40-3*t} 61 Q50 ${72+2*t} ${60+3*t} 61 Q50 65 ${40-3*t} 61Z"/>`;
 if(m==='face-cheeks')b+=`<path d="M30 48 Q${22-3*t} 60 36 64 M70 48 Q${78+3*t} 60 64 64"/>`;
 if(m==='jaw-open')b+=ellipse(50,64,9,2+3*t);}
 else if(v==='neck'){b=path('M42 70 L55 54 L54 42')+`<g transform="rotate(${m==='neck-screen'?-15*t:30*t} 54 43)">${ellipse(54,27,13,17)}${path('M65 24 l6 7 -7 2')}</g>`+path('M42 70 L24 83 M42 70 L64 85');}
 else if(v==='ear'){b=path('M55 12 Q30 5 29 30 Q23 44 36 63 Q37 84 52 74 Q70 62 65 43 Q79 13 55 12Z M53 24 Q39 14 39 33 Q58 22 57 44 Q42 40 47 56 M43 61 Q55 68 55 53')+circle(52,46,4);}
 else if(v==='fundus'){b=ellipse(37,44,17,21)+path('M50 32 Q62 44 50 56 M50 40 Q55 44 50 48')+line(54,44,84,30,'guide');}
 else if(v==='nose'){b=path('M43 15 L36 49 Q21 67 41 70 Q50 76 59 70 Q79 67 64 49 L57 15 M50 56 V72')+ellipse(40,63,5,3)+ellipse(60,63,5,3);}
 else if(v==='mouth'){b=ellipse(50,50,29,26)+ellipse(50,62,19,13)+path('M27 42 Q39 29 48 35 Q50 48 52 35 Q61 29 73 42 M31 49 L35 56 M69 49 L65 56');if(m==='tongue'||m==='tongue-side')b+=`<ellipse cx="${50+(m==='tongue-side'?12*Math.sin(u*6.28):0)}" cy="${65+9*t}" rx="9" ry="${6+5*t}"/>`;}
 else if(v==='jvp'){b=line(20,63,55,83,'table')+line(55,83,91,83,'table')+path('M54 74 L36 54 L27 48 Q18 49 16 41 Q10 29 23 27 Q34 24 38 35 L35 44 L47 49 L69 69 L87 71')+line(37,43,46,56,'guide')+circle(53,56,1.7);b+=txt(76,92,'30–45° recline');}
 else if(v==='arm'||v==='wrist'){b=path('M24 12 Q32 10 35 21 L51 43 L73 67 L83 72 L81 84 L68 78 L43 55 L18 26Z')+circle(48,47,3)+line(50,48,73,71,'guide');if(v==='wrist')b=path('M34 10 L33 45 Q25 50 29 65 L39 80 Q50 88 62 80 L70 62 Q70 50 63 45 L63 10 M34 44 L63 44 M39 54 L56 73 M59 50 L46 75');if(m==='elbow')b=`<g transform="rotate(${-20*t} 48 47)">${b}</g>`;}
 else if(v==='hand'){b=path('M38 90 L35 70 L24 54 Q20 47 25 45 Q30 43 39 53 L33 22 Q31 14 36 14 Q41 14 43 37 L42 13 Q42 6 47 8 Q51 9 51 36 L54 13 Q56 7 60 11 L60 40 L65 22 Q70 15 73 20 L69 53 Q72 78 62 88Z');if(m==='alternating'){const turn=Math.cos(u*2*Math.PI*8),scale=(turn<0?-1:1)*Math.max(.08,Math.abs(turn));b=`<g transform="translate(${50*(1-scale)} 0) scale(${scale} 1)">${b}${turn<0?path('M39 60 Q50 70 63 60'):path('M40 47 V60 M49 45 V60 M59 45 V60')}</g>`+txt(50,99,turn>0?'Palm down on thigh':'Back of hand on thigh')+line(23,92,77,92,'table');}if(m==='hand-spread')b+=arrow(32,27,22,20)+arrow(68,27,79,20);}
 else if(v==='foot'||v==='sole'){b=path('M33 25 Q28 14 36 13 Q40 3 47 11 Q54 3 60 13 Q68 8 70 21 Q81 18 76 31 L66 64 Q71 85 56 90 Q38 96 37 81 L40 57 Q34 44 33 25Z')+path('M39 31 Q51 26 68 33');if(v==='foot')b+=line(48,26,54,69,'guide');if(m==='toe-position')b=path('M28 63 H70 L75 80 H28Z')+line(35,63,46,48,'limb')+line(46,48,46+15*Math.cos(.25*t),48-10*t,'limb')+hand(43,51,0)+hand(58,49-10*t,0);if(m==='ankle')b=`<g transform="rotate(${15*Math.sin(6.28*u)} 53 72)">${b}</g>`;}
 else if(v==='knee-reflex'){b=line(12,46,46,46,'table')+line(24,46,24,88,'table')+line(17,39,60,39,'limb')+line(60,39,60,82,'limb')+line(60,82,73,85,'limb')+circle(60,40,5)+path('M61 45 L62 52');}
 else if(v==='ankle'){b=path('M38 10 L65 10 L62 51 Q64 62 78 67 Q90 77 80 84 L29 85 Q20 83 22 73 L38 48Z')+circle(49,51,4)+path('M63 40 L64 56 L58 65');}
 else if(v==='legs'){b=path('M30 10 L48 10 L46 43 L45 53 L43 89 L28 89 L31 50Z M52 10 L70 10 L69 50 L72 89 L57 89 L55 53 L54 43Z')+ellipse(38,45,6,7)+ellipse(62,45,6,7);if(m==='heel-shin')b+=line(36,18,37,40,'limb')+line(37,40,62,mix(45,83,t),'limb')+ellipse(62,mix(45,83,t),4,2);}
 else if(v==='joint'){b=path('M35 10 L62 10 Q68 33 60 44 Q69 57 62 83 L36 83 Q30 58 39 44 Q30 32 35 10Z')+ellipse(50,43,11,13);if(m.startsWith('region'))b=`<g transform="rotate(${m==='region-extend'?-15*t:25*t} 50 43)">${b}</g>`;}
 else if(v==='chart'){b=path('M22 12 H78 V87 H22Z')+txt(50,27,'SUPPLIED VITALS')+['BP · Pulse','Respirations','Temperature','Oxygen saturation'].map((x,i)=>txt(50,43+i*10,x)).join('');}
 else b=rig(st,u);
 if(m.startsWith('region')&&['back','torso'].includes(v))b=`<g transform="rotate(${(m==='region-side'?18:m==='region-extend'?-12:12)*t} 50 75)">${b}</g>`;
 return `<g class="anatomy">${b}</g>`;
}
function arrow(x,y,a,b){return line(x,y,a,b,'arrow')+`<path class="arrow" d="M${a-2} ${b-3} L${a} ${b} L${a+2} ${b-3}"/>`;}
function hand(x,y,lift=0,kind='finger'){
 const d=kind==='pads'?'M-4 10 L-5 1 L-5 -6 Q-4 -9 -2 -7 L-1 -1 L0 -8 Q2 -11 3 -8 L4 0 L6 0 Q8 1 7 5 L4 12Z':kind==='palm'?'M-6 3 L-6 -3 Q-6 -5 -4 -4 L-4 -7 Q-3 -9 -2 -7 L-2 -9 Q0 -11 1 -8 L2 -8 Q4 -9 4 -6 L5 -5 Q7 -5 7 -2 L7 3 L4 9 L-2 9Z':'M-3 12 L-6 7 Q-8 4 -6 3 L-2 6 L-2 -1 Q-2 -4 0 -4 Q2 -4 2 -1 L2 3 L4 0 Q6 -2 7 0 L7 9 L4 14Z';
 return `<g class="examiner-hand" transform="translate(${x} ${y-lift})">${path(d)}</g>`;
}
function tool(st,u){
 const pts=st.points,act=st.action;
 if(act==='resist'&&['hip-resist','knee','arm-abduct','shrug','elbow-resist','wrist-resist','ankle-resist','grip'].includes(st.motion))return '';
 if(st.wait_until&&u<1-5/st.seconds)return txt(50,98,'Standing observation · '+Math.floor(st.wait_until-st.seconds+u*st.seconds)+' seconds');if(act==='move'||act==='speak')return (act==='speak'&&st.view==='ear'?hand(50,48,0):'')+(st.prompt?txt(50,98,st.prompt):'');
 if(act==='observe'||act==='wait')return pts.map(p=>ellipse(p[0],p[1],10,8)).join('').replaceAll('<ellipse','<ellipse class="observation"');
 const n=pts.length,k=Math.min(n-1,Math.floor(u*n)),local=u*n-k;
 let [x,y]=pts[k];let lift=local<.16?mix(8,0,ease(local/.16)):local>.87?mix(0,8,(local-.87)/.13):0;
 if(act==='trace'||act==='stroke'||act==='fundoscope'||act==='otoscope'||act==='blade'){const z=u*(n-1),j=Math.min(n-2,Math.floor(z));if(n>1){x=mix(pts[j][0],pts[j+1][0],ease(z-j));y=mix(pts[j][1],pts[j+1][1],ease(z-j));}lift=0;}
 let s='';
 if(act==='listen'||act==='bell')s=`<g class="equipment">${path(`M${x+1} ${y-3} Q${x+15} ${y-24} ${x+20} ${y-8}`)}${circle(x,y-lift,act==='bell'?3:4)}${circle(x,y-lift,1.3)}</g>`;
 else if(act==='light')s=`<g class="equipment">${path(`M${x-18} ${y-7} l12 4 -2 5 -12 -4Z`)}<path class="light-beam" d="M${x-6} ${y-3} L${x+4} ${y-6} L${x+4} ${y+5} L${x-8} ${y+2}Z"/></g>`;
 else if(act==='ruler')s=`<g class="equipment">${line(54,55,54,22)}${line(40,49,67,49)}${Array.from({length:10},(_,i)=>line(54,25+i*3,57,25+i*3)).join('')}</g>`;
 else if(act==='measure')s=`<g class="equipment">${line(pts[0][0],pts[0][1],pts.at(-1)[0],pts.at(-1)[1])}${pts.map(p=>circle(...p,2)).join('')}</g>`;
 else if(act==='cva')s=hand(x,y,0,'palm')+`<g class="examiner-hand" transform="translate(${x+1} ${y-7-Math.abs(Math.sin(local*12.56))*6})">${path('M-5 1 Q-7 -5 -3 -6 H4 Q7 -3 6 3 L3 7 L-4 6Z')}</g>`;
 else if(act==='percuss')s=hand(x,y,0)+hand(x+2,y-2,Math.abs(Math.sin(local*Math.PI*4))*7);
 else if(act==='calf-tape')s=`<g class="equipment">${ellipse(u<.5?38:62,57,8,3)}${line(u<.5?30:54,57,u<.5?46:70,57)}</g>`;
 else if(act==='hammer')s=(st.thumb?hand(x,y,0):'')+`<g class="equipment" transform="translate(${x} ${y}) rotate(${-25+35*Math.sin(local*12.56)})">${path('M0 0 L16 -15 M-4 -4 L4 4 L7 1 L-1 -7Z')}</g>`;
 else if(act==='vibrate')s=`<g class="equipment" transform="translate(${x} ${y})">${path(`M0 0 L0 -10 M0 -10 Q-5 -10 -5 -16 V-26 M0 -10 Q5 -10 5 -16 V-26`)}${line(-8-1*Math.sin(local*100),-24,-8,-14,'guide')}${line(8,-24,8+1*Math.sin(local*100),-14,'guide')}</g>`;
 else if(act==='cotton'||act==='pin'||act==='stroke')s=`<g class="equipment">${line(x,y-lift,x+12,y-14-lift)}${act==='cotton'?circle(x,y-lift,3):circle(x,y-lift,1)}</g>`;
 else if(act==='otoscope'||act==='fundoscope')s=`<g class="equipment" transform="translate(${x} ${y})">${path('M0 0 L8 -4 L13 -4 L13 5 L9 5 L8 21 L3 21 L3 4Z')}${circle(9,0,2)}</g>`+ (act==='otoscope'?hand(35,22,0):'');
 else if(act==='blade')s=`<g class="equipment">${path(`M${x-3} ${y-3} h6 v25 h-6Z`)}</g>`;
 else if(act==='cuff')s=`<g class="equipment">${path(`M${x-6} ${y-5} h12 v12 h-12Z M${x+6} ${y+2} Q${x+20} ${y+5} ${x+18} ${y+18}`)}${circle(x+18,y+18,5)}${line(x+18,y+18,x+20,y+15)}</g>`;
 else if(act==='chart')s=`<g class="equipment">${path('M8 18 H28 V50 H8Z')}${txt(18,30,'E')}${txt(18,40,'F P')}</g>`+hand(x,y,0,'palm');
 else if(act==='fluctuance'||act==='fremitus')s=pts.slice(k%2?k-1:k,k%2?k+1:k+2).map(p=>hand(...p,0,'palm')).join('');
 else if(act==='refill'){s=local<.62?hand(x,y,0):ellipse(x,y,7,5);}
 else if(act==='lid')s=hand(x,y+2*tSafe(u),0);
 else if(act==='swallow')s=`<g class="guide" transform="translate(0 ${-4*Math.sin(Math.PI*local)})">${path('M44 77 Q39 85 44 88 L49 85 H51 L56 88 Q61 85 56 77 L51 82 H49Z')}</g>`+hand(44,84,0)+hand(56,84,0)+arrow(50,91,50,88-4*Math.sin(Math.PI*local));
 else s=hand(x+(act==='palpate'?1.2*Math.sin(local*12.56):0),y+(act==='palpate'?1.2*Math.cos(local*12.56):0),lift+(act==='release'&&local>.55?12:0),['palm','backhand','deep','hold','resist'].includes(act)?'palm':['palpate','pulse'].includes(act)?'pads':'finger');
 if(st.observe)s+=st.observe.map(p=>`<ellipse class="observation" cx="${p[0]}" cy="${p[1]}" rx="9" ry="7"/>`).join('');
 return s;
}
function tSafe(u){return Math.sin(Math.PI*u);}
function frame(plan,elapsed,focus){let at=0,index=plan.steps.length-1,st=plan.steps[index],u=1;for(let i=0;i<plan.steps.length;i++){const x=plan.steps[i];if(elapsed<at+x.seconds){index=i;st=x;u=clamp((elapsed-at)/x.seconds);break;}at+=x.seconds;}
 if(st.view==='region'&&(st.motion||'').startsWith('region-'))st={...st,caption:jointMotion(st,u,focus||'back').caption};
 const head=['head','ear','fundus','nose','mouth','neck'].includes(st.view),isBack=st.view==='back';
 let artwork=body(st,u,focus)+`<g class="tools">${tool(st,u)}</g>`;if(st.mirror)artwork=artwork.replace(/<text x="([\d.]+)"/g,(_,x)=>`<text transform="translate(100 0) scale(-1 1)" x="${100-Number(x)}"`);
 const svg=`<svg viewBox="-5 -7 110 112" role="img" aria-label="${esc(st.caption)}"><g ${st.mirror?'transform="translate(100 0) scale(-1 1)"':''}>${artwork}</g>${!['jvp','leg','supine','ear','fundus','neck','chart'].includes(st.view)?txt(10,9,isBack?'L':'R')+txt(90,9,isBack?'R':'L'):''}</svg>`;
 return {svg,index,caption:st.caption,local:u,stage:st,elapsed};
}
let current=null;
function close(){if(!current)return;const old=current;cancelAnimationFrame(current.raf);const owned=old.host.contains(document.activeElement)||(old.returnFocus&&document.activeElement===document.body);current.host.remove();if(owned)requestAnimationFrame(()=>{const usable=old.restore?.isConnected&&!old.restore.disabled&&old.restore.matches('button,input,textarea,select,a[href],[tabindex]')&&old.restore.getClientRects().length;const to=usable?old.restore:document.querySelector('#manSearch');to?.focus({preventScroll:true});});document.querySelector('#ewPanelExam')?.classList.remove('has-exam-animation');current=null;}
function mount(s,preview){close();const pending=s.pending_exam,plan=preview||pending?.demonstration;if(!plan)return;
 const panel=document.querySelector('#ewPanelExam');if(!panel)return;
 const host=document.createElement('section');host.className='exam-demo';host.setAttribute('aria-label',preview?'Teaching replay':'Examination demonstration');
 host.innerHTML=`<div class="exam-demo-meta"><span>Technique model · findings appear separately</span><span class="exam-demo-time"></span></div><p class="exam-demo-position">${esc(plan.position)}</p><div class="exam-demo-stage"><div class="exam-demo-canvas"></div><div class="exam-demo-copy"><small class="exam-demo-step"></small><p class="exam-demo-caption" aria-live="polite"></p><span class="exam-demo-mode">${preview?'Teaching replay · does not perform an examination':'Examination in progress'}</span></div></div><progress max="1" value="0" aria-label="Examination animation progress"></progress><div class="exam-demo-bottom"><button class="btn sm ghost exam-demo-cancel" type="button">${preview?'Exit replay':'Cancel examination'}</button><span class="exam-demo-help">${preview?'No findings or time charge':s.phase_ends_at?'Skip uses the remaining examination time':'Untimed practice'}</span><button class="btn sm ghost exam-demo-skip" type="button">Skip animation</button></div><p class="exam-demo-error" role="alert" hidden></p>`;
 panel.insertBefore(host,document.querySelector('.ew-exam-scroll'));panel.classList.add('has-exam-animation');
 const focus=focusFor(s.case_id);current={sid:s.id,id:pending?.id,host,plan,focus,preview:!!preview,started:preview?Date.now():pending.started_at,restore:document.activeElement,duration:preview?plan.duration_s:pending.duration_s,offset:(s.server_now||Date.now())-Date.now(),busy:false,raf:0,lastStage:-1,lastFrame:0,reduced:window.matchMedia('(prefers-reduced-motion: reduce)').matches};
 host.querySelector('.exam-demo-cancel').onclick=()=>preview?close():control('cancel');host.querySelector('.exam-demo-skip').onclick=()=>preview?close():control('skip');
 tick();
}
function focusFor(id){if(/hand/.test(id))return 'hand';if(/shoulder/.test(id))return 'torso';if(/knee/.test(id))return 'joint';if(/back|flank/.test(id))return 'back';if(/skin/.test(id))return 'arm';return 'back';}
function tick(stamp=0){const c=current;if(!c||!c.host.isConnected){close();return;}if(stamp&&stamp-c.lastFrame<66){c.raf=requestAnimationFrame(tick);return;}c.lastFrame=stamp;const elapsed=clamp((Date.now()+c.offset-c.started)/(c.duration*1000))*c.duration;
 // Saved pending durations retain their original completion time after updates.
 const f=frame(c.plan,elapsed/c.duration*c.plan.duration_s,c.focus);
 if(!c.reduced||c.lastStage!==f.index)c.host.querySelector('.exam-demo-canvas').innerHTML=(c.reduced?frame(c.plan,c.plan.steps.slice(0,f.index).reduce((a,x)=>a+x.seconds,0)+f.stage.seconds*.5,c.focus):f).svg;
 if(c.lastStage!==f.index){c.host.querySelector('.exam-demo-caption').textContent=f.caption;c.host.querySelector('.exam-demo-step').textContent=`${f.index+1} / ${c.plan.steps.length}`;c.lastStage=f.index;}
 c.host.querySelector('progress').value=elapsed/c.duration;
 c.host.querySelector('.exam-demo-time').textContent=`${Math.ceil(Math.max(0,c.duration-elapsed))}s / ${c.duration}s`;
 c.host.dataset.stage=String(f.index);c.host.dataset.elapsed=elapsed.toFixed(3);
 if(elapsed>=c.duration){c.host.querySelector('.exam-demo-mode').textContent=c.preview?'Replay finished · no examination performed':'Finishing · waiting for the recorded result';if(c.preview){c.host.querySelector('.exam-demo-skip').textContent='Replay again';c.host.querySelector('.exam-demo-skip').onclick=()=>{c.started=Date.now();c.offset=0;tick();};}return;}
 c.raf=requestAnimationFrame(tick);
}
async function control(operation){const c=current;if(!c||c.preview||c.busy)return;c.returnFocus=c.host.contains(document.activeElement);c.busy=true;c.host.querySelectorAll('button').forEach(b=>b.disabled=true);
 try{const r=await api('/api/session/'+c.sid+'/exam_control',{examination_id:c.id,operation});if(current!==c||S?.id!==c.sid)return;if(r.error)throw new Error(r.message||'The examination control was not saved.');const oldPhase=S.phase;if(r.state)S={...S,...r.state};if(S.phase!==oldPhase){stopVoice();cancelRunningExam();clearPendingReveals();renderPhase(true);return;}if(r.state?.transcript)paintStream(S.transcript);paintExamProgress();notifyPublicState();}
 catch(e){if(current===c){const error=c.host.querySelector('.exam-demo-error');error.hidden=false;error.textContent='Could not '+(operation==='skip'?'skip':'cancel')+' the examination. Check your connection and try again.';}}
 finally{c.busy=false;if(current===c)c.host.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
function sync(s){if(!s||s.phase!=='encounter'){close();return;}const p=s.pending_exam;if(p){if(!p.demonstration){close();return;}if(!current||current.sid!==s.id||current.id!==p.id||!current.host.isConnected||current.preview)mount(s);}
 else if(current&&!current.preview)close();}
window.PCMExamAnimation={sync,close,frame,preview:(s,plan)=>mount(s,plan)};
})();
