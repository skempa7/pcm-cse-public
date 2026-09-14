const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8773/web/';
const output=process.env.CSE_TEST_OUTPUT||require('node:os').tmpdir()+'/cse-browser-review';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:process.env.CSE_BROWSER||'chrome',headless:true});
 const ctx=await browser.newContext({viewport:{width:1366,height:900}});
 await ctx.addInitScript(()=>{
  class Recognition {
   constructor(){window.testRecognition=this;this.starts=0;this.running=false;}
   start(){if(this.running)throw Error('already running');this.running=true;this.starts++;this.onstart?.();}
   stop(){this.running=false;this.onend?.();}abort(){this.running=false;this.onend?.();}
   fail(){this.onerror?.({error:'not-allowed'});this.running=false;this.onend?.();}
  }
  window.SpeechRecognition=Recognition;
 });
 const p=await ctx.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base);await p.locator('[data-portal-go=practice]').first().click({timeout:120000});await p.locator('#btnStart').waitFor();
 await p.evaluate(()=>begin(false,{case_id:'cardio-febrile-cough',variant_id:'base',learning_mode:'guided',mode:'voice'}));
 await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();
 // Real button events use a controlled recognizer; no actual microphone needed.
 await p.locator('#btnMic').click();await p.locator('#btnMic').click();await p.waitForTimeout(600);
 assert.equal(await p.evaluate(()=>testRecognition.starts),0);
 await p.locator('#btnMic').click();await p.waitForFunction(()=>voice.listening);
 await p.evaluate(()=>testRecognition.fail());await p.locator('[data-act=retry]').click();
 await p.waitForFunction(()=>testRecognition.starts===2&&voice.listening);
 await p.locator('#say').press('Escape');assert.equal(await p.evaluate(()=>voice.wanted),false);await p.waitForTimeout(600);assert.equal(await p.evaluate(()=>testRecognition.starts),2);
 console.log('PASS actual mic clicks, permission-error retry and Escape cancellation');
 // The provider returns a storage failure after the user starts the next draft.
 await p.evaluate(()=>{window.auditFetch=window.fetch;window.fetch=async(i,o)=>String(i).endsWith('/say')?new Promise(r=>window.rejectTurn=()=>r(new Response(JSON.stringify({error:'storage_unavailable',message:'Test storage failure'}),{status:503}))):window.auditFetch(i,o);});
 await p.locator('#say').fill('What brings you in today?');await p.locator('#btnSay').click();await p.waitForFunction(()=>typeof rejectTurn==='function');await p.locator('#say').fill('When did it start?');await p.evaluate(()=>rejectTurn());
 await p.waitForFunction(()=>document.querySelector('#say').value==='What brings you in today?\nWhen did it start?');
 await p.evaluate(()=>{window.fetch=window.auditFetch});
 assert.match(await p.locator('#say').inputValue(),/When did it start/);
 await p.reload();await p.locator('#say').waitFor({timeout:120000});assert.equal(await p.locator('#say').inputValue(),'What brings you in today?\nWhen did it start?');
 await p.locator('#say').fill('');console.log('PASS failed question and newer draft survive failure and reload');
 for(const question of ["What's your name and age and what brings you in today?",'When did it start?','Any shortness of breath?', 'Let me summarize: the cough began 2 days ago.']){
  await p.locator('#say').fill(question);await p.locator('#btnSay').click();await p.waitForFunction(q=>S.transcript.some(t=>t.kind==='student_utterance'&&t.text===q),question);await p.waitForFunction(()=>!document.querySelector('#btnSay').disabled);
  const reply=await p.evaluate(()=>S.transcript.filter(t=>t.kind==='patient_reply').at(-1)?.text||'');
  if(question==='Any shortness of breath?')assert.match(reply,/stairs/i);
  if(question.startsWith('Let me summarize:')){assert.match(reply,/4 days|four days/i);assert.doesNotMatch(reply,/that.s (?:right|correct)/i);}
 }
 console.log('PASS packaged dialogue: compound identity, direct ROS, and correction of a wrong timeline');
 await p.locator('[data-ew-tab=record]').click();assert(await p.locator('#ewRecordLog').innerText());
 assert.deepEqual((await p.locator('.ew-oldcarts-title').allTextContents()).filter(t=>/^[OLDCARTS] · /.test(t)),['O · Onset','L · Location / radiation','D · Duration','C · Character','A · Aggravating factors','R · Relieving factors','T · Timing / course','S · Severity']);
 assert.match(await p.locator('#ewRecordLog').innerText(),/stairs/i);
 await p.locator('[data-ew-tab=exam]').click();await p.locator('[data-exam-action]').filter({hasText:'General appearance'}).first().click();
 await p.waitForFunction(()=>!!S.pending_exam);assert(await p.getByRole('button',{name:'Standing',exact:true}).isDisabled());
 await p.waitForFunction(()=>!S.pending_exam&&S.transcript.some(e=>e.kind==='exam_finding'),{},{timeout:20000});
 await p.waitForTimeout(1500);assert.match(await p.locator('#ewExamOutcome').innerText(),/findings/);assert(await p.locator('#ewTabrecord .ew-new-badge').count());
 await p.locator('[data-ew-tab=record]').click();assert.equal(await p.locator('#ewTabrecord .ew-new-badge').count(),0);
 await p.locator('[data-ew-tab=exam]').click();
 for(const [width,height] of [[1366,900],[1093,614],[390,844]]){
  await p.setViewportSize({width,height});await p.waitForTimeout(1000);
  const sizes=await p.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth,board:document.querySelector('.ew-exam-scroll').getBoundingClientRect().height}));
  assert(sizes.scroll<=sizes.width+1,JSON.stringify(sizes));assert(sizes.board>=100,JSON.stringify(sizes));
  const action=p.locator('[data-exam-action]:visible').last();await action.click({trial:true});assert(await action.isVisible());
  const box=await action.boundingBox();assert(box&&box.y>=0&&box.y+box.height<=height+1,JSON.stringify(box));
  await p.locator('#ewPanelExam').evaluate(el=>el.scrollTop=0);
  await p.locator('.ew-exam-scroll').evaluate(el=>el.scrollTop=0);await p.evaluate(()=>window.scrollTo(0,0));
  await p.screenshot({path:path.join(output,`review-exam-${width}.png`),fullPage:true});
 }
 console.log('PASS one-click examination, position lock, findings, Notes alert and responsive layouts');
 await p.setViewportSize({width:1366,height:900});
 await p.locator('#btnBrand').click();await p.getByRole('button',{name:'Stay here',exact:true}).click();await p.waitForTimeout(400);assert.equal(await p.evaluate(()=>S.phase),'encounter');
 await p.locator('#btnEnd').click();await p.getByRole('button',{name:'End encounter',exact:true}).click();await p.locator('#noteS').waitFor();
 await p.locator('#noteS').fill('Patient reports cough starting four days ago.');
 await p.locator('#noteO').fill('General appearance as examined; other findings not assessed.');
 await p.locator('#noteA0').fill('Respiratory illness; cause requires further assessment.');
 await p.locator('#noteP0').fill('Discuss the findings with the supervising clinician.');
 await p.waitForFunction(()=>noteSave.state==='saved');const sid=await p.evaluate(()=>S.id);
 await p.reload();await p.locator('#noteS').waitFor({timeout:120000});assert.equal(await p.locator('#noteS').inputValue(),'Patient reports cough starting four days ago.');
 await p.locator('#btnSubmit').click();await p.locator('.confirm-dialog button[value=confirm]').click();await p.waitForFunction(()=>S.phase==='submitted'&&RESULTS?.__for===S.id,{},{timeout:30000});
 assert.equal(await p.evaluate(()=>S.id),sid);assert.equal(await p.evaluate(()=>RESULTS.results.versions.recorded.engine),'4.2.1');await p.screenshot({path:path.join(output,'review-feedback.png'),fullPage:true});
 await p.locator('#btnBrand').click();await p.waitForFunction(()=>document.body.dataset.workspace==='home');
 const resume=p.locator('[data-resume="'+sid+'"]');assert(await resume.count());
 console.log('PASS cancel Home, finish encounter, note save/reload, submit feedback, Home and saved attempt');
 await p.locator('[data-destination=cases]').click();await p.locator('#materialGrid .lesson-card').first().waitFor();await p.locator('#materialGrid .lesson-card').first().click();await p.locator('.material-details summary').click();await p.getByRole('link',{name:'Read the demonstrated encounter and source references →'}).click();await p.locator('#printLesson').click();await p.locator('#preparePrintDocument').click();await p.waitForFunction(()=>document.body.hasAttribute('data-walkthrough-preview'),{},{timeout:30000});
 const print=await p.evaluate(()=>window.pcmPrintReport);assert.equal(print.oversized.length,0);assert(print.pages>0);await p.screenshot({path:path.join(output,'review-print.png'),fullPage:false});
 console.log('PASS rendered written walkthrough and print preview',JSON.stringify({pages:print.pages,images:print.images,oversized:print.oversized.length}));
 // Exercise course-timed note writing and the solution assistance boundary.
 await p.keyboard.press('Escape');await p.locator('#btnBrand').click();await p.waitForFunction(()=>document.body.dataset.workspace==='home');
 await p.locator('[data-portal-go=practice]').first().click();await p.locator('#btnStart').waitFor();
 await p.evaluate(()=>begin(false,{case_id:'renal-flank-pain',variant_id:'base',learning_mode:'rehearsal',mode:'type'}));
 await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();
 assert.equal(await p.evaluate(()=>S.preset.encounter_s),840);
 await p.locator('#btnEnd').click();await p.locator('.confirm-dialog button[value=confirm]').click();await p.locator('#noteS').waitFor();
 assert.equal(await p.evaluate(()=>S.phase),'note');assert.equal(await p.evaluate(()=>S.preset.note_s),540);
 const protectedId=await p.evaluate(()=>S.id),deadline=await p.evaluate(()=>S.phase_ends_at);
 await p.locator('#noteS').fill('Protected draft remains saved.');await p.waitForFunction(()=>noteSave.state==='saved');
 await p.evaluate(()=>location.hash='#learn');await p.locator('.confirm-dialog').waitFor();
 assert.match(await p.locator('.confirm-dialog').innerText(),/assisted practice/i);
 await p.locator('.confirm-dialog button[value=cancel]').click();await p.waitForURL('**/#/'+protectedId);await p.waitForFunction(()=>document.body.dataset.workspace==='encounter'&&!document.querySelector('.confirm-dialog'));await p.locator('#noteS').waitFor();
 assert.equal(await p.evaluate(()=>S.assisted),false);assert.equal(await p.locator('#noteS').inputValue(),'Protected draft remains saved.');assert.equal(await p.evaluate(()=>S.phase_ends_at),deadline);
 await p.evaluate(()=>location.hash='#learn');await p.locator('.confirm-dialog button[value=confirm]').click();await p.locator('.lesson-card').first().waitFor();
 const saved=await p.evaluate(async id=>(await fetch('/api/session/'+id)).json(),protectedId);
 assert.equal(saved.assisted,true);assert.equal(saved.phase_ends_at,deadline);assert.equal(saved.note.S,'Protected draft remains saved.');
 console.log('PASS course timing, saved protected note, canceled solution access and explicit assisted access preserving deadline');
 const duplicate=await ctx.newPage();await duplicate.goto(base);await duplicate.waitForFunction(()=>document.body.innerText.includes('already open in another tab'),{},{timeout:20000});await duplicate.close();
 assert.deepEqual(errors,[]);console.log('PASS duplicate-tab protection; no page JavaScript errors');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
