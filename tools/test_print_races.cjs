/* Latency failures around visible print actions; every browser has disposable storage. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert/strict'),fs=require('fs'),path=require('path'),os=require('os'),crypto=require('crypto');
const root=path.resolve(__dirname,'..');
const sourceHashes=()=>Object.fromEntries(['web/study.js','web/walkthrough-print.js','web/walkthrough-print.css','web/partner-print.js','web/engine.zip'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8775/web/';
const out=process.env.CSE_TEST_OUTPUT||path.join(os.tmpdir(),'cse-print-races');
fs.mkdirSync(out,{recursive:true});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};};
(async()=>{
 const initialSource=sourceHashes();
 const browser=await chromium.launch({channel:'chrome',headless:true});const results=[];
 async function scenario(name,run){
  const context=await browser.newContext({viewport:{width:1440,height:900},serviceWorkers:'block'});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  try{await run(page);assert.deepEqual(errors,[],name+' browser errors');results.push({name,result:'PASS'});}
  finally{await context.close();}
 }
 async function home(p){await p.locator('#btnBrand').click();await p.waitForFunction(()=>location.hash==='#home'&&document.body.dataset.workspace==='home');await p.locator('#view .portal-dashboard').waitFor({timeout:15000});}
 async function cases(p){await p.locator('[data-destination=cases]').click();await p.locator('#materialGrid .lesson-card').first().waitFor({timeout:120000});}
 async function choose(p,cid){await p.locator('#materialGrid a[href="#cases/'+cid+'"]').click();await p.locator('#material-student').waitFor();}
 async function ready(p){await p.goto(base+'#home');await p.locator('#view .portal-dashboard').waitFor({timeout:120000});}
 async function settle(p){await p.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
 async function assertHome(p){await settle(p);assert.equal(await p.evaluate(()=>location.hash),'#home');assert(await p.locator('#view .portal-dashboard').isVisible());assert.equal(await p.locator('body[data-walkthrough-preview]').count(),0);assert.equal(await p.locator('#walkthroughPrint').count(),0);assert.equal(await p.title(),'Chat CSE');}
 async function holdResponse(p,mode){
  await p.evaluate(mode=>{
   const original=window.fetch;let release;
   window.__printRace={held:false,resumed:false,release:()=>release?.()};
   window.fetch=async(...args)=>{
    const url=String(args[0]);
    const hold=!window.__printRace.held&&(mode==='index'?url==='/api/printables':url.endsWith('/api/teaching/status')&&!!window.pcmPrintReport);
    const response=await original(...args);
    if(hold&&!window.__printRace.held){window.__printRace.held=true;await new Promise(r=>release=r);window.__printRace.resumed=true;}
    return response;
   };
  },mode);
 }
 await scenario('Delayed printable index cannot replace Home',async p=>{
  await ready(p);await holdResponse(p,'index');await p.locator('[data-destination=cases]').click();
  await p.waitForFunction(()=>window.__printRace.held);await home(p);
  await p.evaluate(()=>window.__printRace.release());await p.waitForFunction(()=>window.__printRace.resumed);await assertHome(p);
 });
 await scenario('Delayed first print module import cannot replace Home',async p=>{
  const held=deferred(),release=deferred();
  await p.route('**/partner-print.js*',async route=>{held.resolve();await release.promise;await route.continue();});
  await ready(p);await cases(p);await p.locator('#materialGrid a[href="#cases/cardio-febrile-cough"]').click();
  await held.promise;await home(p);release.resolve();await p.waitForResponse(r=>r.url().includes('/partner-print.js'));
  await assertHome(p);
 });
 await scenario('Older preparation cannot replace or clear a newer case preview',async p=>{
  const held=deferred(),release=deferred();
  await p.route('**/walkthrough-print.css*',async route=>{held.resolve();await release.promise;await route.continue();});
  await ready(p);await cases(p);await choose(p,'cardio-febrile-cough');await p.locator('#material-student').click();
  await held.promise;await home(p);await cases(p);await choose(p,'renal-flank-pain');await p.locator('#material-blank').click();
  release.resolve();await p.waitForFunction(()=>document.body.hasAttribute('data-walkthrough-preview'));
  await settle(p);assert.equal(await p.locator('#walkthroughPrint').count(),1);assert.equal(await p.evaluate(()=>pcmPrintReport.case_id),'renal-flank-pain');assert.equal(await p.evaluate(()=>pcmPrintReport.edition),'blank');
  assert.match(await p.title(),/Maya Ellison/);await p.locator('#pwClosePrint').click();assert.equal(await p.evaluate(()=>document.activeElement.id),'material-blank');
  assert.equal(await p.locator('#walkthroughPrint').count(),0);assert(await p.locator('#material-patient').isEnabled());
 });
 await scenario('Delayed final access verification cannot reopen answers after leaving',async p=>{
  await ready(p);await cases(p);await choose(p,'cardio-febrile-cough');await holdResponse(p,'final');
  await p.locator('#material-patient').click();await p.waitForFunction(()=>window.__printRace.held,{},{timeout:30000});
  assert.equal(await p.locator('body[data-walkthrough-preview]').count(),0);await home(p);
  await p.evaluate(()=>window.__printRace.release());await p.waitForFunction(()=>window.__printRace.resumed);await assertHome(p);
 });
 await browser.close();assert.deepEqual(sourceHashes(),initialSource,'Build changed during race verification');fs.writeFileSync(path.join(out,'races.json'),JSON.stringify({source:initialSource,results,limits:'Injected latency verifies stale UI isolation; these tests do not claim screen-reader compliance or real-user usability.'},null,2));
 console.log('PASS',results.length,'visible print interruption races');
})().catch(error=>{console.error(error);process.exit(1);});
