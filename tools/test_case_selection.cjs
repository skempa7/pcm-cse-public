/* Actual, disposable browser workflows: grouped selection, artwork, tablet reflow and sealed cases. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8786/web/';
const out=process.env.CSE_TEST_OUTPUT||path.join(require('node:os').tmpdir(),'cse-case-selection');fs.mkdirSync(out,{recursive:true});
const expected={'Cardiovascular':[2,'cardio'],'Cardiopulmonary':[4,'cardiopulmonary'],'Respiratory':[3,'pulmonary'],'Gastrointestinal':[6,'gi'],'Renal / Genitourinary':[6,'renal'],'Neurologic':[6,'neuro'],'Musculoskeletal':[3,'msk'],'HEENT':[2,'heent'],'Skin':[2,'skin']};
const root=path.resolve(__dirname,'..');const hashes=()=>Object.fromEntries(['web/portal.js','web/portal.css','web/learning.js','web/study.js','web/app.js'].map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex')]));
(async()=>{
 const source=hashes(),b=await chromium.launch({channel:process.env.CSE_BROWSER||'chrome',headless:true});
 const ctx=await b.newContext({viewport:{width:820,height:1180},isMobile:true,hasTouch:true,deviceScaleFactor:1});
 const p=await ctx.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base+'#practice');await p.locator('#filterCount').waitFor({timeout:120000});
 assert.equal(await p.locator('.station-card').count(),34);assert.equal(await p.locator('.station-system').count(),9);
 const initialOrder=await p.locator('.station-card input').evaluateAll(a=>a.map(x=>x.value));
 const grouped=await p.locator('.station-system').evaluateAll(a=>a.map(s=>({system:s.dataset.system,count:s.querySelectorAll('.station-card').length,kinds:[...s.querySelectorAll('.s-illustration svg')].map(x=>x.dataset.organ)})));
 assert.deepEqual(grouped.map(x=>x.system),Object.keys(expected));
 for(const s of grouped){assert.equal(s.count,expected[s.system][0]);assert(s.kinds.every(k=>k===expected[s.system][1]),JSON.stringify(s));}
 // Touch selection keeps its identity through filtering and a mode change.
 await p.locator('[data-family="Musculoskeletal"]').tap();await p.locator('[data-case="msk-hand-stiffness"]').tap();
 assert.equal(await p.locator('input[name=station]:checked').inputValue(),'msk-hand-stiffness');
 await p.locator('[data-family="Skin"]').tap();assert.equal(await p.locator('.station-card:visible').count(),2);assert.equal(await p.locator('.station-system:visible').count(),1);
 assert.equal(await p.locator('input[name=station]:checked').inputValue(),'msk-hand-stiffness');assert.match(await p.locator('#lobbyChosen').innerText(),/selected outside this filter/);
 await p.locator('[data-family=""]').tap();assert.equal(await p.locator('.station-card:visible').count(),34);
 assert(!/outside this filter/.test(await p.locator('#lobbyChosen').innerText()));
 await p.locator('[data-mode="rehearsal"]').tap();assert.equal(await p.locator('.station-system').count(),0);assert.equal(await p.locator('.portal-families:visible').count(),0);assert.equal(await p.locator('#stationGrid .s-title').count(),0);
 assert(await p.locator('#stationGrid .s-illustration').evaluateAll(a=>a.every(x=>x.dataset.kind==='sealed')));
 assert.doesNotMatch(await p.locator('#stationGrid').innerText(),/Musculoskeletal|HEENT|Skin|Respiratory|hand stiffness|wristwatch/i);
 assert.match(await p.locator('#lobbyChosen').innerText(),/contents sealed/);
 const sealedNumbers=await p.locator('.station-card .station-no').allTextContents();assert.deepEqual(sealedNumbers.map(x=>Number(x.match(/\d+/)[0])),Array.from({length:34},(_,i)=>i+1));
 await p.screenshot({animations:'disabled',path:path.join(out,'sealed-selector.png')});await p.locator('[data-mode="coached"]').tap();
 assert.equal(await p.locator('input[name=station]:checked').inputValue(),'msk-hand-stiffness');assert.deepEqual(await p.locator('.station-card input').evaluateAll(a=>a.map(x=>x.value)),initialOrder);
 // Every SVG is square, centered in its cell and entirely inside its declared canvas.
 const artwork=await p.locator('.station-card .s-illustration svg').evaluateAll(a=>a.map(svg=>{const box=svg.getBBox(),r=svg.getBoundingClientRect(),c=svg.closest('.s-illustration').getBoundingClientRect();return {kind:svg.dataset.organ,bounds:[box.x,box.y,box.width,box.height],width:r.width,height:r.height,x:r.x,cx:c.x};}));
 for(const a of artwork){assert(Math.abs(a.width-a.height)<.5,JSON.stringify(a));assert(a.bounds[0]>=0&&a.bounds[1]>=0&&a.bounds[0]+a.bounds[2]<=140&&a.bounds[1]+a.bounds[3]<=140,JSON.stringify(a));assert.equal(a.x,a.cx);}
 const viewports=[[768,1024],[1024,768],[820,1180],[1180,820],[1440,900],[640,800]];
 const layouts=[];
 for(const [width,height] of viewports){
  await p.setViewportSize({width,height});await p.locator('[data-family=""]').tap();await p.locator('.station-system[data-system="Musculoskeletal"]').scrollIntoViewIfNeeded();
  const result=await p.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,cards:[...document.querySelectorAll('.station-card:not([hidden])')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,width:r.width,overflow:e.scrollWidth>e.clientWidth+1};}),filters:[...document.querySelectorAll('.portal-family')].map(e=>e.getBoundingClientRect().height)}));
  assert(result.scroll<=result.width+1,JSON.stringify(result));assert(result.cards.every(c=>c.x>=0&&c.x+c.width<=result.width+1&&!c.overflow),JSON.stringify(result));assert(result.filters.every(h=>h>=44));const heading=await p.locator('.station-head').evaluate(e=>({sticky:getComputedStyle(e).position==='sticky',top:e.getBoundingClientRect().top,navBottom:document.querySelector('.topbar').getBoundingClientRect().bottom}));if(heading.sticky)assert(heading.top>=heading.navBottom-1,JSON.stringify(heading));layouts.push({width,height,cards:result.cards.length});
  await p.screenshot({animations:'disabled',path:path.join(out,`practice-${width}x${height}.png`)});
 }
 // A chosen radio remains keyboard operable after the layout and filters change.
 const radio=p.locator('[data-case="msk-hand-stiffness"] input');await radio.focus();await p.keyboard.press('ArrowRight');assert.notEqual(await p.locator('input[name=station]:checked').inputValue(),'msk-hand-stiffness');await p.keyboard.press('ArrowLeft');assert.equal(await p.locator('input[name=station]:checked').inputValue(),'msk-hand-stiffness');
 await p.locator('#btnStart').tap();await p.locator('#skipEntrance').waitFor();assert.match(await p.locator('.doorway').innerText(),/Amina Reed/);
 // Main navigation and safe print case list use the identical system order and artwork.
 await p.locator('#btnBrand').tap();await p.locator('.confirm-dialog[open] button[value=confirm]').tap();await p.waitForFunction(()=>document.body.dataset.workspace==='home');
 await p.locator('[data-destination="cases"]').tap();await p.locator('#materialGrid .lesson-card').first().waitFor();
 assert.equal(await p.locator('#materialGrid .lesson-card').count(),34);assert.deepEqual(await p.locator('.case-library-system').evaluateAll(a=>a.map(x=>x.dataset.system)),Object.keys(expected));
 await p.locator('#materialSearch').fill('knee');assert.equal(await p.locator('#materialGrid .lesson-card').count(),1);assert.equal(await p.locator('#materialGrid svg').getAttribute('data-organ'),'msk');await p.locator('#materialGrid .lesson-card').tap();await p.locator('#material-patient').waitFor();await p.getByRole('link',{name:'← All cases'}).tap();await p.locator('#materialSystem').selectOption('Skin');assert.equal(await p.locator('#materialGrid .lesson-card').count(),2);assert.equal(await p.locator('.case-library-system').count(),1);assert.equal(await p.locator('#materialGrid svg').first().getAttribute('data-organ'),'skin');await p.locator('#materialSystem').selectOption('');
 for(const [width,height] of viewports){await p.setViewportSize({width,height});await p.locator('.case-library-system[data-system="Musculoskeletal"]').scrollIntoViewIfNeeded();assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));const boxes=await p.locator('#materialGrid .lesson-card').evaluateAll(a=>a.map(e=>({scroll:e.scrollWidth,client:e.clientWidth,x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right})));assert(boxes.every(x=>x.scroll<=x.client+1&&x.x>=0&&x.right<=width+1),JSON.stringify(boxes));await p.screenshot({animations:'disabled',path:path.join(out,`materials-${width}x${height}.png`)});}
 await p.locator('#themeToggle').tap();await p.waitForFunction(()=>getComputedStyle(document.querySelector('[data-destination=cases]')).backgroundColor==='rgb(41, 72, 61)');await p.screenshot({animations:'disabled',path:path.join(out,'materials-evening.png')});
 assert.deepEqual(errors,[]);assert.deepEqual(hashes(),source,'Source changed during the selector run; rerun against a stable candidate.');
 fs.writeFileSync(path.join(out,'selector-results.json'),JSON.stringify({result:'PASS',source,groups:grouped,layouts,checks:['all 34 cases in nine authored systems','new anatomical icons and bounded square artwork','touch selection and retained filtered selection','sealed labels/icons/order and selected caption','keyboard radio traversal','selected case opens its actual doorway','safe material navigation/search/filter','tablet portrait/landscape and 640px/desktop reflow','day/evening capture'],errors},null,2));await b.close();console.log('PASS 34 grouped cases, artwork, sealed mode, selection, keyboard/touch and six viewports');
})().catch(e=>{console.error(e);process.exit(1)});
