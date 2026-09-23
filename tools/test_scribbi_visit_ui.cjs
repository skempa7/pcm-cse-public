/* Scribbi visits in a real browser: read, watch (the visit player) and lead
   (the Chat CSE room with Scribbi listening), plus resuming a visit left open.
   Uses a disposable browser profile.

   CSE_TEST_URL=http://127.0.0.1:8773/web/ node tools/test_scribbi_visit_ui.cjs */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8773/web/';
const out=process.env.CSE_TEST_OUTPUT||path.join(require('node:os').tmpdir(),'cse-scribbi-visit');fs.mkdirSync(out,{recursive:true});
const ready=p=>p.waitForFunction(()=>document.getElementById('localEngineStatus')?.textContent.includes('Saved on this browser'),null,{timeout:90000});
const shot=(p,n)=>p.screenshot({path:path.join(out,n+'.png')});
const api=(p,path,body)=>p.evaluate(([path,body])=>api(path,body),[path,body]);

(async()=>{
 const browser=await chromium.launch({channel:process.env.CSE_BROWSER||'chrome',headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const passed=[];
 const context=await browser.newContext({viewport:{width:1440,height:900}});
 const page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'#scribbi');await ready(page);await page.waitForSelector('.sb-hero');

 // Home: three ways to see the visit, three reviews.
 assert.equal(await page.locator('[data-style]').count(),3);
 assert.equal(await page.locator('[data-mode]').count(),3);
 for(const [style,label] of [['read','Open the draft'],['lead','Enter the room'],['watch','Start the visit']]){
  await page.click(`[data-style=${style}]`);assert.match(await page.locator('#sbStart').innerText(),new RegExp(label));
  assert.equal(await page.locator(`[data-style=${style}]`).getAttribute('aria-checked'),'true');
 }
 passed.push('home offers watch, lead and read, and the start button follows the choice');

 // Read: straight to the draft, with a way to watch.
 await page.click('[data-style=read]');await page.click('[data-mode=learn]');await page.click('[data-patient="renal-flank-pain"]');
 await page.click('#sbStart');await page.waitForSelector('#sbDraft .sb-chip',{timeout:30000});
 assert.ok(await page.locator('.sb-watch').isVisible());
 passed.push('read opens the draft directly, with a Watch link to the visit');

 // Watch: the player.
 await page.click('.sb-watch');await page.waitForSelector('.sv-stage');
 await page.waitForSelector('.sv-cover .sv-bigplay');
 const src=await page.locator('.sv-frame').getAttribute('src');
 assert.match(src,/viewer=1/);assert.match(src,/env=studio/);
 await page.waitForFunction(()=>document.querySelector('.sv-stage')?.classList.contains('has-room'),null,{timeout:120000});
 await shot(page,'watch-cover');
 await page.click('.sv-bigplay');
 await page.waitForFunction(()=>document.querySelector('.sv-shell')?.dataset.state==='playing');
 const first=await page.locator('#svLine').innerText();
 await page.waitForFunction(f=>document.querySelector('#svLine')?.textContent!==f,first,{timeout:15000});
 passed.push('watch plays the visit with captions that advance line by line');
 await page.keyboard.press('Space');
 await page.waitForFunction(()=>document.querySelector('.sv-shell')?.dataset.state==='paused');
 const exam=await page.evaluate(()=>Number([...document.querySelectorAll('.sv-item.is-exam')][1]?.dataset.beat));
 await page.click(`[data-seek="${exam}"]`);
 assert.equal(await page.locator('.sv-item.is-now').getAttribute('data-beat'),String(exam));
 await page.keyboard.press('Space');await page.waitForSelector('#svPip:not([hidden])',{timeout:8000});
 await shot(page,'watch-exam');
 passed.push('Space pauses and resumes; the transcript seeks; exams show the technique');
 const felt=await page.evaluate(()=>Number(document.querySelector('.sv-item.is-felt')?.dataset.beat));
 await page.click(`[data-seek="${felt}"]`);
 await page.waitForFunction(()=>!document.querySelector('#svBubble')?.hidden&&/palpation/.test(document.querySelector('#svBubble').textContent),null,{timeout:15000});
 await shot(page,'watch-felt');
 passed.push('palpation plays silently and Scribbi says it cannot hear it');
 await page.click('.sv-skip');
 await page.waitForSelector('#sbDraft .sb-chip',{timeout:30000});
 passed.push('skipping ahead opens the review');

 // A watched round: its clock waits for the visit.
 const watched=await api(page,'/api/scribbi/rounds',{case_id:'renal-flank-pain',variant_id:'base',mode:'solo',timed:true,watch:true});
 assert.equal(watched.started,false);assert.equal(watched.deadline,null);
 await page.evaluate(id=>{location.hash='#scribbi/r/'+id;},watched.id);
 await page.waitForSelector('.sv-stage');
 passed.push('an unstarted watched review opens the visit first');
 await page.click('.sv-cover [data-sv=skip]');await page.waitForSelector('#sbClock',{timeout:30000});
 const begun=await api(page,'/api/scribbi/rounds/'+watched.id);
 assert.equal(begun.started,true);assert.ok(begun.deadline>Date.now()+200000);
 passed.push('the solo clock starts only when the review begins');

 // Lead: the Chat CSE room, with Scribbi listening.
 await page.goto(base+'#scribbi');await page.waitForSelector('.sb-hero');
 await page.click('[data-style=lead]');await page.click('[data-mode=coached]');await page.click('[data-patient="renal-flank-pain"]');
 await page.selectOption('#sbVariant','base');
 await page.click('#sbStart');
 await page.waitForSelector('.scribbi-door-note',{timeout:60000});
 await shot(page,'lead-doorway');
 await page.click('#skipEntrance');await page.waitForSelector('#say',{timeout:60000});
 assert.ok(await page.locator('.scribbi-listening').isVisible());
 assert.match(await page.locator('#btnEnd').innerText(),/Scribbi writes the note/);
 assert.equal(await page.locator('[data-destination=scribbi]').getAttribute('aria-current'),'page');
 const ask=async q=>{const before=await page.locator('#stream .turn.pt').count();await page.fill('#say',q);await page.click('#btnSay');await page.waitForFunction(n=>document.querySelectorAll('#stream .turn.pt').length>n,before,{timeout:20000});};
 await ask('Hi, I am a student doctor. What brings you in today?');await ask('When did it start?');
 await page.click('#btnEnd');await page.click('dialog.confirm-dialog button[value=confirm]');
 await page.waitForFunction(()=>/a little more/.test(document.querySelector('.toast')?.textContent||''),null,{timeout:15000});
 assert.equal(await page.evaluate(()=>S?.phase),'encounter');
 passed.push('finishing too early explains what Scribbi still needs and keeps the visit open');
 for(const q of ['Does the pain go anywhere?','How bad is the pain from 0 to 10?','Have you had shaking chills?','Any nausea or vomiting?'])await ask(q);
 await page.click('[data-ew-tab=exam]');
 const run=async key=>{const tile=page.locator(`[data-exam-action="${key}"]`);if(!await tile.isVisible())await page.click('#ewExamAll');await tile.click();await page.waitForSelector('.exam-demo-skip',{timeout:15000});await page.click('.exam-demo-skip');await page.waitForFunction(()=>!S.pending_exam,null,{timeout:20000});};
 await run('general_inspect:complete');await run('abd_special:5');
 await shot(page,'lead-room');
 passed.push('the led visit runs in the room: questions, exams, Scribbi listening');
 await page.click('#btnEnd');await page.click('dialog.confirm-dialog button[value=confirm]');
 await page.waitForSelector('#sbDraft .sb-chip',{timeout:30000});
 assert.ok(await page.locator('.sb-yours').isVisible());
 assert.equal(await page.evaluate(()=>typeof S==='undefined'?null:S),null);
 await shot(page,'lead-review');
 passed.push('finishing hands the visit to Scribbi: the draft of your own visit opens');
 const boot=await api(page,'/api/bootstrap');
 assert.equal((boot.sessions||[]).length,0);
 passed.push('a led visit is not a Chat CSE attempt');

 // Leaving a led visit open, then resuming it from Scribbi.
 await page.goto(base+'#scribbi');await page.waitForSelector('.sb-hero');
 await page.click('[data-style=lead]');await page.click('#sbQuick');
 await page.waitForSelector('#skipEntrance',{timeout:60000});await page.click('#skipEntrance');await page.waitForSelector('#say',{timeout:60000});
 const sid=await page.evaluate(()=>S.id);
 assert.equal((await page.locator('#btnHome').innerText()).trim(),'Scribbi');
 await page.click('#btnHome');await page.click('dialog.confirm-dialog button[value=confirm]');
 await page.waitForSelector('.sb-resume-visit',{timeout:30000});
 await page.click('[data-resume-visit]');await page.waitForSelector('#say',{timeout:60000});
 assert.equal(await page.evaluate(()=>S.id),sid);
 passed.push('a visit left open waits on the Scribbi home and resumes in the room');
 await page.click('#btnHome');await page.click('dialog.confirm-dialog button[value=confirm]');
 await page.waitForSelector('.sb-hero');await page.click('[data-destination=home]');
 await page.waitForFunction(()=>[...document.querySelectorAll('.portal-mode.is-scribbi button')].some(b=>b.textContent==='Back to the room'),null,{timeout:30000});
 await page.locator('.portal-mode.is-scribbi button',{hasText:'Back to the room'}).click();
 await page.waitForSelector('#say',{timeout:60000});assert.equal(await page.evaluate(()=>S.id),sid);
 passed.push('the Home page offers the open visit too');

 // Phone: the player fits.
 await page.goto('about:blank');await page.setViewportSize({width:390,height:844});
 await page.goto(base+'#scribbi/r/'+watched.id+'/visit');await ready(page);await page.waitForSelector('.sv-stage');await page.waitForTimeout(800);
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
 assert.ok(overflow<=1,'no horizontal scroll: '+overflow);
 await shot(page,'watch-phone');
 passed.push('the player fits a phone without horizontal scroll');

 assert.deepEqual(errors,[],'page errors: '+errors.join('; '));
 passed.push('no page JavaScript errors');
 await browser.close();
 console.log(passed.map(p=>'PASS '+p).join('\n'));
})().catch(e=>{console.error(e);process.exit(1);});
