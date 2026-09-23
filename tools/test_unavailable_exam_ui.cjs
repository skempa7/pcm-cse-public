/* Visible JVD attempt that has no finding, in a disposable browser profile.
   Since the 2026-09-14 routine expansion every visible action in the current
   library has an authored result, so the profile is seeded with one unfinished
   guided attempt saved before it: its own case snapshot is the pre-expansion
   content the unit tests use, stored where the browser engine keeps attempts.
   The engine and the page then run unmodified. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),os=require('node:os'),{execFileSync}=require('node:child_process');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8776/web/';
const output=process.env.CSE_TEST_OUTPUT||path.join(require('node:os').tmpdir(),'cse-unavailable-exam');
const source=path.resolve(__dirname,'../web/encounter-workspace.js');
const engineFile=path.resolve(__dirname,'../web/engine.zip');
const [width,height]=(process.env.CSE_TEST_VIEWPORT||'1440x900').split('x').map(Number);
const touch=process.env.CSE_TEST_TOUCH==='1',rotate=process.env.CSE_TEST_ROTATE==='1';
const activate=locator=>touch?locator.tap():locator.click();
const digest=data=>crypto.createHash('sha256').update(data).digest('hex');
// The app's own routes create the guided attempt; only its saved snapshot and
// version stamps are replaced with those of an attempt begun under engine 4.2.6.
const SEED=`import json,os,sys
root=sys.argv[1];sys.path[:0]=[root,os.path.join(root,'tests')]
from pcmcse import db,version
db.init()
from offline_routes import request
from sparse_case_fixtures import without_supplemental_content
def call(path,body):
    r=json.loads(request(path,'POST',json.dumps(body)));assert r['status']==200,(path,r);return r['body']
sid=call('/api/session',{'case_id':'cardio-palpitations','learning_mode':'guided'})['id']
with db.connect() as conn:
    current=json.loads(conn.execute('SELECT case_snapshot FROM sessions WHERE id=?',(sid,)).fetchone()[0])
    legacy=without_supplemental_content(current)
    assert current['exam_findings'].get('jvd') and not legacy['exam_findings'].get('jvd')
    conn.execute('UPDATE sessions SET case_snapshot=?,case_version=?,app_version=?,engine_version=? WHERE id=?',(json.dumps(legacy),version.case_version(legacy),'4.2.6','4.2.6',sid))
call('/api/session/'+sid+'/start',{})
print(sid)`;
function seedAttempt(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cse-legacy-attempt-')),file=path.join(dir,'attempts.sqlite');
 const sid=execFileSync(process.env.PYTHON||'python3',['-B','-c',SEED,path.resolve(__dirname,'..')],{env:{...process.env,PCM_CSE_DB:file,PCM_CSE_SETTINGS:path.join(dir,'settings.json')},encoding:'utf8'}).trim();
 return {sid,bytes:fs.readFileSync(file)};
}
(async()=>{
 const sourceHash=digest(fs.readFileSync(source)),engineHash=digest(fs.readFileSync(engineFile));
 if(process.env.CSE_EXPECT_ENGINE_SHA)assert.equal(engineHash,process.env.CSE_EXPECT_ENGINE_SHA,'Local engine differs from the requested final build.');
 const seeded=seedAttempt();
 const browser=await chromium.launch({channel:process.env.CSE_BROWSER||'chrome',headless:true});
 const context=await browser.newContext({viewport:{width,height},hasTouch:touch,isMobile:touch}),errors=[],engineDownloads=[];
 context.on('response',response=>{if(/\/engine\.zip(?:\?|$)/.test(response.url()))engineDownloads.push(response.body().then(body=>({url:response.url(),hash:digest(body)})));});
 let page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 try{
  // The first visit creates the engine's storage; the saved attempt then
  // replaces its attempts.sqlite while no page holds the engine.
  await page.goto(base+'#practice');
  await page.locator('#filterCount').waitFor({timeout:120000});
  assert(await page.locator('#btnResume').isHidden());
  await page.close();
  page=await context.newPage();
  await page.goto(new URL('app.webmanifest',base).href);
  await page.evaluate(async bytes=>{
   const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('/pcm-cse-public-v1');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
   if(!db.objectStoreNames.contains('FILE_DATA'))throw Error('Unexpected browser engine storage layout.');
   await new Promise((resolve,reject)=>{const tx=db.transaction('FILE_DATA','readwrite');tx.objectStore('FILE_DATA').put({timestamp:new Date(),mode:0o100644,contents:new Uint8Array(bytes)},'/pcm-cse-public-v1/attempts.sqlite');tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
   db.close();
  },[...seeded.bytes]);
  await page.close();
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'#practice');
  await page.locator('#filterCount').waitFor({timeout:120000});
  await activate(page.locator('#btnResume'));
  await page.locator('#say').waitFor({timeout:120000});
  const sid=await page.evaluate(()=>S.id);
  assert.equal(sid,seeded.sid);
  await activate(page.locator('[data-ew-tab=exam]'));
  const tile=page.locator('[data-exam-action="jvd:complete"]');
  if(!await tile.isVisible())await activate(page.locator('#ewExamRegions [data-region-jump="Heart"]'));
  assert(await tile.isVisible());
  assert.equal(await tile.locator('.ew-unavailable-flag').isVisible(),false);
  await activate(tile);
  await tile.locator('.ew-unavailable-flag').waitFor({state:'visible',timeout:25000});
  assert.equal(await tile.locator('.ew-done-flag').isVisible(),false);
  assert.equal(await tile.getAttribute('class').then(s=>s.includes('is-done')),false);
  assert.match(await page.locator('#ewExamOutcome').innerText(),/attempt is recorded.*no finding.*does not mean/is);
  assert.match(await page.locator('#manCount').innerText(),/1 without findings/);
  const status=()=>page.evaluate(()=>({actions:S.examination_activity.filter(e=>e.meta.maneuver_id==='jvd').map(e=>e.meta.status),findings:S.transcript.filter(e=>e.kind==='exam_finding'&&e.meta.maneuver_id==='jvd').length}));
  assert.deepEqual(await status(),{actions:['in_progress','not_simulated'],findings:0});
  await activate(page.locator('[data-ew-tab=talk]'));
  await page.locator('#say').fill('My next question is not sent yet.');
  await activate(page.locator('[data-ew-tab=exam]'));
  if(!await tile.isVisible())await activate(page.locator('#ewExamRegions [data-region-jump="Heart"]'));
  assert(await tile.locator('.ew-unavailable-flag').isVisible());
  const expandAll=await page.locator('#ewExamAll').isVisible()&&await page.locator('#ewExamAll').innerText()==='All actions';
  if(expandAll)await activate(page.locator('#ewExamAll'));
  await page.locator('#manSearch').fill('jugular');
  assert.match(await page.locator('#manCount').innerText(),/^1 actions · 1 without findings/);
  assert(await tile.locator('.ew-unavailable-flag').isVisible());
  await page.locator('#manSearch').fill('');
  if(expandAll)await activate(page.locator('#ewExamAll'));
  await activate(page.locator('[data-ew-tab=record]'));
  assert.doesNotMatch(await page.locator('#ewRecordLog').innerText(),/jugular|no jvd/i);
  await page.reload();await page.locator('[data-ew-tab=talk]').waitFor({timeout:120000});
  assert.equal(await page.evaluate(()=>S.id),sid);
  await activate(page.locator('[data-ew-tab=talk]'));
  assert.equal(await page.locator('#say').inputValue(),'My next question is not sent yet.');
  await activate(page.locator('[data-ew-tab=exam]'));
  if(!await tile.isVisible())await activate(page.locator('#ewExamRegions [data-region-jump="Heart"]'));
  assert(await tile.locator('.ew-unavailable-flag').isVisible());
  assert.equal(await tile.locator('.ew-done-flag').isVisible(),false);
  assert.deepEqual(await status(),{actions:['in_progress','not_simulated'],findings:0});
  fs.mkdirSync(output,{recursive:true});
  await tile.scrollIntoViewIfNeeded();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Ordinary content must not require horizontal scrolling.');
  await page.screenshot({path:path.join(output,'jvd-unavailable-'+width+'x'+height+'.png')});
  if(rotate){
   await page.setViewportSize({width:height,height:width});
   await tile.scrollIntoViewIfNeeded();
   assert(await tile.locator('.ew-unavailable-flag').isVisible());
   assert.equal(await page.locator('#say').inputValue(),'My next question is not sent yet.');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Rotation must preserve readable reflow.');
  }
  // An ordinary successful examination retains its distinct performed status.
  const general=page.locator('[data-exam-action="general_inspect:complete"]');
  await activate(general);await general.locator('.ew-done-flag').waitFor({state:'visible',timeout:25000});
  assert.equal(await general.locator('.ew-unavailable-flag').isVisible(),false);
  assert.match(await page.locator('#manCount').innerText(),/1 already performed · 1 without findings/);
  fs.mkdirSync(output,{recursive:true});
  await tile.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'jvd-attempt-status.png')});
  assert.deepEqual(errors,[]);
  const served=await page.request.get(new URL('encounter-workspace.js',base).href);
  assert.equal(digest(await served.body()),sourceHash,'The browser server must serve the changed workspace source.');
  assert.equal(digest(fs.readFileSync(source)),sourceHash,'Source changed during the check.');
  const fetchedEngine=await page.request.get(new URL('engine.zip',base).href);
  assert(fetchedEngine.ok());assert.equal(digest(await fetchedEngine.body()),engineHash,'Server engine bytes differ from this final build.');
  const downloads=await Promise.all(engineDownloads);
  assert(downloads.length>0,'The browser must actually download its engine during the disposable encounter.');
  assert(downloads.every(d=>d.hash===engineHash),'The running encounter downloaded an earlier engine package.');
  assert.equal(digest(fs.readFileSync(engineFile)),engineHash,'Engine package changed during the check.');
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({sourceHash,engineHash,downloads,viewport:{width,height},touch,rotated:rotate?{width:height,height:width}:null,case:'cardio-palpitations',seeded_attempt:{sid:seeded.sid,snapshot:'pre-expansion case content (tests/sparse_case_fixtures.py)',versions:'4.2.6'},checks:['saved pre-expansion attempt resumes from the lobby','unavailable not disclosed before attempting','visible JVD action completes without a finding','no performed mark or Notes finding','tile and count survive task switches, filter and reload','unsent Talk draft preserved','successful general examination remains performed'],errors},null,2));
  console.log('PASS visible unavailable-exam status, counts, filtering, reload, Notes evidence boundary and distinct completed status');
 }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
