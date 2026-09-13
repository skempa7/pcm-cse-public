/* Disposable UI journeys: fixtures only start an attempt; visible controls do the work. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=process.env.CSE_TEST_OUTPUT||'/private/tmp/cse-assistance-workspace';fs.mkdirSync(output,{recursive:true});
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8775/web/';
async function openGuide(p){await p.locator('#encounterGuide').waitFor({state:'attached'});if(!await p.locator('#ewPanelGuide').evaluate(el=>el.open))await p.locator('#ewPanelGuide > summary').click();}

let debugPage;
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});
for(const mode of ['coached','guided']){
const c=await b.newContext({viewport:{width:1440,height:900}}),errors=[];let p=await c.newPage();debugPage=p;p.on('pageerror',e=>{errors.push(e.message);console.log('PAGE ERROR',e.message)});await p.goto(base);await p.locator('[data-portal-go=practice]').first().click({timeout:120000});await p.locator('#btnStart').waitFor();await p.evaluate(mode=>begin(false,{case_id:'cardio-febrile-cough',variant_id:'base',learning_mode:mode,mode:'type'}),mode);await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();await openGuide(p);await p.locator('#encounterGuide').waitFor();
if(mode==='coached'){
 await p.getByRole('button',{name:'Choose a move',exact:true}).click();await p.locator('dialog [data-step=pattern]').click();await p.waitForFunction(()=>document.querySelector('#guidePurpose')?.dataset.selectedStage==='pattern');
 const before=await p.locator('.coach-move').innerText();assert.match(before,/begin|start/i);await p.locator('.coach-why summary').click();await p.locator('#say').fill('When did it start?');await p.locator('#btnSay').click();await p.waitForFunction(()=>!document.querySelector('#btnSay').disabled);await p.waitForFunction(()=>document.querySelector('#guidePurpose')?.dataset.hasNextSuggestion==='true');
 assert.equal(await p.locator('.coach-move').innerText(),before);assert(await p.locator('.coach-why').evaluate(el=>el.open));await p.locator('#say').fill('My unfinished question stays here.');
 await p.locator('#coachDraft').click();assert.equal(await p.locator('#say').inputValue(),'My unfinished question stays here.');assert.equal(await p.locator('.coach-conflict').count(),0);assert.equal(await p.locator('.coach-progress').count(),0);
 await p.screenshot({path:path.join(output,'coach-draft-conflict.png')});
 await p.reload();await p.locator('#say').waitFor({timeout:120000});await p.locator('.coach-move').waitFor({state:'attached'});await openGuide(p);await p.locator('.coach-move').waitFor();assert.equal(await p.locator('.coach-move').innerText(),before);
 const resumeUrl=p.url();await p.close();p=await c.newPage();debugPage=p;p.on('pageerror',e=>errors.push(e.message));await p.goto(resumeUrl);await p.locator('#say').waitFor({timeout:120000});await openGuide(p);assert.equal(await p.locator('.coach-move').innerText(),before);
 await p.locator('#coachRecommend').click();assert.notEqual(await p.locator('.coach-move').innerText(),before);
 console.log('PASS coached choice remains pinned after question, reload, and new-tab resume, rationale stays open, next recommendation explicit, existing draft intact');
}else{
 await p.locator('#ewGuideMore').click();const choices=await p.locator('#guideJump option').evaluateAll(opts=>opts.map(o=>({id:o.value,text:o.textContent})));const onset=choices.find(o=>/when did.*(?:begin|start)/i.test(o.text));assert(onset,JSON.stringify(choices.slice(0,20)));await p.locator('#guideJump').selectOption(onset.id);await p.waitForFunction(id=>document.querySelector('#guideJump')?.value===id,onset.id);await p.locator('.guide-why summary').click();
 const before=await p.locator('.guide-current blockquote').innerText();await p.locator('#say').fill('When did it start?');await p.locator('#btnSay').click();await p.waitForFunction(()=>!document.querySelector('#btnSay').disabled);await p.waitForTimeout(1000);assert.equal(await p.locator('.guide-current blockquote').innerText(),before);assert(await p.locator('.guide-why').evaluate(el=>el.open));assert.match(await p.locator('.guide-current-label').innerText(),/Evidence recorded/);
 await p.locator('#say').fill('My unfinished question stays here.');await p.locator('#guideDraft').click();assert.equal(await p.locator('#say').inputValue(),'My unfinished question stays here.');
 await p.screenshot({path:path.join(output,'guided-draft-conflict.png')});await p.reload();await p.locator('#say').waitFor({timeout:120000});await p.locator('.guide-current blockquote').waitFor({state:'attached'});await openGuide(p);await p.locator('.guide-current blockquote').waitFor();assert.equal(await p.locator('.guide-current blockquote').innerText(),before);
 await p.screenshot({path:path.join(output,'guided-selected-move.png')});await p.locator('#guideNext').click();await p.waitForFunction(id=>document.querySelector('#guideJump')?.value!==id,onset.id);await p.locator('#guidePrevious').click();await p.waitForFunction(id=>document.querySelector('#guideJump')?.value===id,onset.id);
 console.log('PASS guided selected task stays after completion and reload, rationale stays open, previous/next preserve navigation');
 // A patient response can complete while a student reads an already-open path.
 await p.evaluate(()=>{window.assistanceRealFetch=window.fetch;window.fetch=async(...args)=>{const response=await assistanceRealFetch(...args);return String(args[0]).endsWith('/say')?new Promise(resolve=>window.releaseAssistanceResponse=()=>resolve(response)):response;};});
 await p.locator('#say').fill('Have you had any shortness of breath?');await p.locator('#btnSay').click();await p.waitForFunction(()=>typeof releaseAssistanceResponse==='function');
 await p.locator('#ewGuideMore').click();const selectedBefore=await p.locator('#guideJump').inputValue();
 await p.evaluate(()=>releaseAssistanceResponse());await p.waitForFunction(()=>!document.querySelector('#btnSay').disabled);await p.waitForTimeout(250);
 assert(await p.locator('dialog #guideJump').isVisible());assert.equal(await p.locator('#guideJump').inputValue(),selectedBefore);
 await p.locator('dialog.ew-sheet .ew-sheet-head button').click();await p.waitForFunction(id=>document.querySelector('#guideJump')?.value===id,selectedBefore);
 await p.evaluate(()=>window.fetch=assistanceRealFetch);await p.locator('#unstuckButton').click();await p.locator('dialog #recoveryBody .recovery-card').waitFor();
 const cue=await p.locator('dialog #recoveryBody h3').innerText();await p.locator('dialog.ew-sheet .ew-sheet-head button').click();await p.locator('#unstuckButton').click();assert.equal(await p.locator('dialog #recoveryBody h3').innerText(),cue);await p.locator('dialog.ew-sheet .ew-sheet-head button').click();
 await p.locator('#btnEnd').click();await p.locator('.confirm-dialog button[value=confirm]').click();await p.locator('#noteS').waitFor();await p.locator('#noteGuideHelp').waitFor();assert.equal(await p.locator('#noteGuideHelp').evaluate(el=>el.open),false);
 const note=await p.locator('#noteS').boundingBox();assert(note&&note.y<900);
 await p.locator('#noteS').fill('Student writing remains my own.');await p.locator('#noteGuideHelp > summary').click();assert(await p.locator('#noteGuideHelp #encounterGuide').isVisible());await p.locator('#noteGuideHelp > summary').click();assert.equal(await p.locator('#noteS').inputValue(),'Student writing remains my own.');
 console.log('PASS path survives delayed response in open sheet, cue reopening, and collapsed note help preserves editor');
}assert.deepEqual(errors,[]);await c.close();}
await b.close()})().catch(async e=>{console.error(e);if(debugPage){console.log(await debugPage.evaluate(()=>({phase:window.S?.phase,mode:window.S?.learning_mode,guide:document.querySelector('#ewPanelGuide')?.outerHTML,full:document.querySelector('#encounterGuide')?.outerHTML})));await debugPage.screenshot({path:path.join(output,'failure.png')});}process.exit(1)});
