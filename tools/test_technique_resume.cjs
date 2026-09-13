/* Visible examination-guide navigation; disposable attempts only. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=process.env.CSE_TEST_OUTPUT||'/private/tmp/cse-technique-resume';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true}),c=await b.newContext({viewport:{width:1440,height:900}});let p=await c.newPage();
 const errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
 await p.goto(process.env.CSE_TEST_URL||'http://127.0.0.1:8775/web/');
 await p.locator('[data-portal-go=practice]').first().click({timeout:120000});await p.locator('#btnStart').waitFor();
 await p.evaluate(()=>begin(false,{case_id:'cardio-febrile-cough',variant_id:'base',learning_mode:'coached',mode:'type'}));
 await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();
 let room=p.frameLocator('#unityFrame');await room.locator('#techniqueLaunch').waitFor();
 const before=await p.evaluate(()=>JSON.stringify(S.transcript));
 await p.evaluate(()=>{window.lessonActions=[];addEventListener('message',e=>{if(e.data?.type==='pcm-unity-teaching')lessonActions.push(e.data);});});
 await room.locator('#techniqueLaunch').click();await room.locator('[data-exam=cardiac]').click();await room.locator('#techNext').click();await room.locator('#techSkip').click();
 await room.locator('#techniquePanel small').filter({hasText:'STEP 3 OF'}).waitFor();const title=await room.locator('#techniquePanel h2').innerText();
 await room.getByRole('button',{name:'Close the examination guide',exact:true}).click();await room.locator('#techniqueLaunch').click();
 assert.equal(await room.locator('#techniquePanel h2').innerText(),title);assert.match(await room.locator('#techniquePanel small').innerText(),/STEP 3 OF/);
 await room.locator('#techMenu').click();await room.locator('#techResume').click();assert.equal(await room.locator('#techniquePanel h2').innerText(),title);
 assert.equal(await p.evaluate(()=>lessonActions.filter(x=>x.event==='start').length),1);
 assert.equal(await p.evaluate(()=>JSON.stringify(S.transcript)),before);
 await p.reload();await p.locator('#say').waitFor({timeout:120000});await room.locator('#techniqueLaunch').waitFor();await room.locator('#techniqueLaunch').click();
 assert.equal(await room.locator('#techniquePanel h2').innerText(),title);
 const resumeUrl=p.url();await p.close();p=await c.newPage();p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());await p.goto(resumeUrl);await p.locator('#say').waitFor({timeout:120000});room=p.frameLocator('#unityFrame');await room.locator('#techniqueLaunch').waitFor();await room.locator('#techniqueLaunch').click();assert.equal(await room.locator('#techniquePanel h2').innerText(),title);
 await room.locator('#techNext').click();await room.locator('#techNext').click();await room.locator('.tech-done').waitFor();
 assert.match(await room.locator('.tech-checks .no').innerText(),/not rehearsed/);
 assert.equal(await p.evaluate(()=>JSON.stringify(S.transcript)),before);
 console.log('PASS close/reopen, reload, and new-tab resume preserve guide step; All examinations/Resume returns; skipped step stays excluded; no clinical findings');
 for(const width of [820,390]){
  await p.setViewportSize({width,height:900});await room.locator('#techAgain').click();await room.locator('#techNext').click();
  await room.locator('#techNext').click({trial:true});await p.screenshot({path:path.join(output,'guide-resumed-'+width+'.png')});
  assert(await room.locator('.tech-demo svg').isVisible());
  await room.getByRole('button',{name:'Close the examination guide',exact:true}).click();await room.locator('#techniqueLaunch').click();assert.match(await room.locator('#techniquePanel small').innerText(),/STEP 2 OF/);
  await room.locator('#techMenu').click();await room.locator('#techResume').click();await room.locator('#techNext').click();await room.locator('#techNext').click();await room.locator('#techNext').click();await room.locator('.tech-done').waitFor();
 }
 await room.getByRole('button',{name:'Close the examination guide',exact:true}).click();await p.setViewportSize({width:1440,height:900});
 await p.locator('#btnBrand').click();await p.locator('.confirm-dialog button[value=confirm]').click();await p.waitForFunction(()=>document.body.dataset.workspace==='home');
 await p.locator('[data-portal-go=practice]').first().click();await p.locator('#btnStart').waitFor();
 await p.evaluate(()=>begin(false,{case_id:'renal-flank-pain',variant_id:'base',learning_mode:'coached',mode:'type'}));await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();await room.locator('#techniqueLaunch').waitFor();await room.locator('#techniqueLaunch').click();
 assert.equal(await room.locator('#techResume').count(),0);assert.match(await room.locator('#techniquePanel h2').innerText(),/Choose an examination/);
 assert.deepEqual(errors,[]);console.log('PASS 820/390 visible navigation and new encounter starts a fresh guide');await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
