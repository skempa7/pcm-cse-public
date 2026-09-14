/* Source-bounded navigation checks + visible controls in disposable encounters. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),file=path.join(root,'web/encounter-workspace.js');
const source=fs.readFileSync(file,'utf8'),hash=crypto.createHash('sha256').update(source).digest('hex');
const start=source.indexOf('function relevantRegions(s){'),end=source.indexOf('\n}\n',start)+2;
assert(start>=0&&end>start);const scope={};vm.runInNewContext(source.slice(start,end)+'; this.getRegions=relevantRegions;',scope);
const regions=s=>{const result=scope.getRegions(s);return result?[...result]:null;};
const skin=['General','Skin','Extremities','HEENT'];
for(const text of ['A red sore patch on my left shin is getting bigger.','Both hands have an itchy rash.','The redness is spreading.','My skin feels irritated.'])assert.deepEqual(regions({learning_mode:'coached',station_chart:{doorway:[text]}}),skin,text);
assert.deepEqual(regions({learning_mode:'guided',transcript:[{kind:'patient_reply',text:'My hands are itching.'}]}),skin);
assert.equal(regions({learning_mode:'coached',hidden_label:'Skin disease',expected_maneuvers:['skin_palpate'],exam_findings:{skin_inspect:{text:'redness'}}}),null);
assert.equal(regions({learning_mode:'coached',transcript:[{kind:'student_utterance',text:'Do you have a rash?'},{kind:'patient_reply',text:'Skin information is unavailable.',meta:{no_information:true}}]}),null);
assert.equal(regions({learning_mode:'rehearsal',station_chart:{doorway:['An itchy rash.']}}),null);
assert.equal(regions({learning_mode:'coached',station_chart:{doorway:['My insurance paperwork needs completing.']}}),null);
const mixed=regions({learning_mode:'coached',station_chart:{doorway:['An itchy rash and shortness of breath.']}});assert(mixed.includes('Lungs')&&mixed.includes('Skin'));assert.deepEqual(mixed.slice(0,3),['General','Skin','Extremities']);
console.log('PASS skin navigation uses delivered symptoms, excludes hidden/unknown/clinician text, and preserves other complaint routes and rehearsal');
if(process.env.CSE_TEST_LOGIC_ONLY==='1')process.exit(0);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8775/web/';
const output=process.env.CSE_TEST_OUTPUT||'/private/tmp/cse-skin-exam-defaults';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true}),results=[];
 try{
  for(const [cid,mode]of [['skin-localized-redness','coached'],['skin-contact-rash','coached'],['skin-localized-redness','rehearsal']]){
   const context=await browser.newContext({viewport:{width:1440,height:900}}),p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
   try{
    await p.goto(base);await p.locator('[data-portal-go=practice]').first().click({timeout:120000});await p.locator('#btnStart').waitFor();
    // Fixture only selects a disposable patient/mode. All examination navigation
    // below uses the rendered interface; no findings or selections are injected.
    await p.evaluate(({cid,mode})=>begin(false,{case_id:cid,variant_id:'base',learning_mode:mode,mode:'type'}),{cid,mode});
    await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();await p.locator('[data-ew-tab=exam]').click();
    const headings=()=>p.locator('#ewExamBoard .ew-action-group h3').allTextContents();
    if(mode==='rehearsal'){
     assert.match(await p.locator('#ewExamScope').innerText(),/Full catalog/);assert.equal(await p.locator('#ewExamAll').isVisible(),false);assert((await headings()).length>skin.length);
    }else{
     assert.deepEqual(await headings(),skin);assert.match(await p.locator('#ewExamScope').innerText(),/Complaint & related/);
     assert(await p.locator('[data-exam-action="skin_palpate:complete"]').isVisible());
     const initial=Number(await p.locator('#manCount').getAttribute('data-total'));
     await p.locator('#ewExamAll').click();const total=Number(await p.locator('#manCount').getAttribute('data-total'));assert(total>initial);assert((await headings()).includes('Abdomen'));
     await p.locator('#manSearch').fill('skin');assert(await p.locator('#ewExamBoard [data-exam-action]').count()>0);assert(await p.locator('#manSearch').isVisible());
     await p.locator('#manSearch').fill('');await p.locator('#ewExamAll').click();assert.deepEqual(await headings(),skin);assert.equal(Number(await p.locator('#manCount').getAttribute('data-total')),initial);
     await p.locator('[data-ew-tab=talk]').click();await p.locator('#say').fill('My unfinished interview question.');await p.locator('[data-ew-tab=exam]').click();assert.deepEqual(await headings(),skin);await p.locator('[data-ew-tab=talk]').click();assert.equal(await p.locator('#say').inputValue(),'My unfinished interview question.');
     await p.locator('[data-ew-tab=exam]').click();await p.screenshot({path:path.join(output,cid+'-'+mode+'.png')});
     results.push({case:cid,mode,focusedActions:initial,allActions:total,groups:skin});
    }
    assert.deepEqual(errors,[]);
   }finally{await context.close();}
  }
 }finally{await browser.close();}
 assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),hash,'Source changed during verification');
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({sourceHash:hash,results,rehearsal:'full catalog retained',limits:'The test checks navigation and draft preservation, not clinical technique or examination result accuracy.'},null,2));
 console.log('PASS visible skin-focused examinations, full catalog/search, Talk draft preservation and unfiltered rehearsal');
})().catch(error=>{console.error(error);process.exit(1);});
