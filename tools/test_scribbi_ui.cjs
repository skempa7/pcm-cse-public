/* Scribbi in a real browser: home, a Learn review with instant feedback, a
   Coached review with hints, signing, the debrief, phone layout and the
   evening theme. Uses a disposable browser profile; nothing touches saved
   work in anyone's own browser.

   CSE_TEST_URL=http://127.0.0.1:8773/web/ node tools/test_scribbi_ui.cjs */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8773/web/';
const wait=ms=>new Promise(r=>setTimeout(r,ms));

async function ready(page){
 await page.waitForFunction(()=>document.getElementById('localEngineStatus')?.textContent.includes('Saved on this browser'),null,{timeout:90000});
}
async function chipByText(page,predicate){
 return page.evaluateHandle(src=>{const fn=new Function('t','return ('+src+')(t)');return [...document.querySelectorAll('#sbDraft .sb-chip')].find(c=>fn(c.textContent));},predicate.toString());
}

(async()=>{
 const browser=await chromium.launch({channel:process.env.CSE_BROWSER||'chrome',headless:true});
 const passed=[];
 const context=await browser.newContext({viewport:{width:1440,height:900}});
 const page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'#home');await ready(page);

 // Home offers both modes.
 await page.waitForSelector('.portal-mode.is-scribbi');
 assert.equal(await page.locator('.portal-mode').count(),2);
 assert.ok(await page.locator('[data-destination=scribbi]').isVisible());
 passed.push('home shows Chat CSE and Scribbi side by side; nav has Scribbi');

 // Scribbi home: modes, patients, start bar.
 await page.click('[data-destination=scribbi]');
 await page.waitForSelector('.sb-hero');
 assert.equal(await page.locator('[data-mode]').count(),3);
 assert.equal(await page.locator('[data-style]').count(),3);
 await page.click('[data-style=read]');
 assert.equal(await page.locator('.sb-patient').count(),35); // 34 presentations + Surprise me
 await page.click('[data-mode=solo]');
 assert.ok(await page.locator('#sbTimerRow').isVisible());
 await page.click('[data-mode=learn]');
 assert.ok(await page.locator('#sbTimerRow').isHidden());
 await page.click('[data-patient="renal-flank-pain"]');
 assert.match(await page.locator('.sb-start-bar').innerText(),/Right flank pain/);
 assert.equal(await page.locator('#sbVariant option').count(),4);
 passed.push('Scribbi home: three ways to see the visit, three reviews, 34 patients, variation picker, timer only for On your own');

 // Learn review.
 await page.click('#sbStart');
 await page.waitForSelector('#sbDraft .sb-chip',{timeout:30000});
 await page.waitForSelector('.sb-coach');
 assert.match(await page.locator('.sb-coach').innerText(),/I made 3 mistakes/);
 assert.match(await page.locator('#sbMeter').innerText(),/0 of 3 found/);
 const firstChip=page.locator('#sbDraft .sb-chip').first();
 await firstChip.click();
 await page.waitForSelector('.sb-pop');
 assert.deepEqual(await page.locator('.sb-pop button').evaluateAll(b=>b.map(x=>x.dataset.act)),['verify','edit','remove','find']);
 await page.keyboard.press('Escape');
 assert.equal(await page.locator('.sb-pop').count(),0);
 passed.push('lines open an action menu (looks right, edit, remove, find) that Escape closes');

 // Find in visit highlights the source.
 await firstChip.click();await page.click('.sb-pop [data-act=find]');
 await page.waitForSelector('#sbVisitBody .is-hit');
 passed.push('Find in visit highlights the supporting moment');

 // Removing a correct line is a false alarm; restoring clears it.
 const vitals=page.locator('#sbDraft .sb-line',{hasText:'Vitals'}).locator('.sb-chip').filter({hasText:/^R \d+/});
 await vitals.click();await page.keyboard.press('r');
 await page.waitForFunction(()=>/That line was right/.test(document.querySelector('.sb-coach')?.innerText||''));
 await vitals.click();await page.click('.sb-pop [data-act=restore]');
 await page.waitForFunction(()=>!document.querySelector('#sbDraft .sb-chip.is-removed'));
 passed.push('removing a correct line is flagged at once and Restore undoes it');

 // Add a structural finding.
 await page.click('[data-add=O]');
 await page.fill('#sbDraft [data-editor] textarea','Osteopathic: T10-L1 right paraspinal tissue texture change and tenderness; T11 rotated right.');
 await page.keyboard.press('Enter');
 await page.waitForSelector('#sbDraft .sb-add-item');
 await page.waitForFunction(()=>/Hands-on finding added/.test(document.querySelector('.sb-coach')?.innerText||''));
 passed.push('an added structural finding is recognized instantly');

 // Edits save and survive a reload.
 await page.waitForFunction(()=>document.getElementById('sbSave')?.textContent==='Saved');
 await page.reload();await ready(page);
 await page.waitForSelector('#sbDraft .sb-add-item');
 passed.push('the review autosaves and resumes after reload');

 // Sign.
 await page.click('#sbSign');
 await page.click('dialog.confirm-dialog button[value=confirm]');
 await page.waitForSelector('.sb-result');
 const hero=await page.locator('.sb-result').innerText();
 assert.match(hero,/Hands-on added/);
 assert.ok(await page.locator('.sb-item').count()>=4);
 assert.ok(await page.locator('[data-next=again]').isVisible());
 passed.push('signing shows the debrief with every mistake and the hands-on item');

 // Coached review with hints.
 await page.goto(base+'#scribbi');await page.waitForSelector('.sb-hero');
 await page.click('[data-mode=coached]');await page.click('#sbStart');
 await page.waitForSelector('#sbHint');
 await page.click('#sbHint');
 await page.waitForFunction(()=>/Hint 1 of 3/.test(document.querySelector('.sb-coach')?.innerText||''));
 assert.equal((await page.locator('#sbHintLeft').innerText()).trim(),'2');
 passed.push('Coached mode gives section hints and counts them down');

 // Phone layout: pane switch.
 await page.setViewportSize({width:375,height:812});
 assert.ok(await page.locator('.sb-pane-switch').isVisible());
 await page.click('.sb-pane-switch [data-pane=visit]');
 assert.ok(await page.locator('.sb-visit').isVisible());
 assert.ok(await page.locator('.sb-draft').isHidden());
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
 assert.ok(overflow<=1,'no horizontal scroll on a phone: '+overflow);
 passed.push('phone layout switches between the visit and the draft without horizontal scroll');

 // Evening theme.
 await page.setViewportSize({width:1440,height:900});
 await page.evaluate(()=>{document.documentElement.dataset.theme='night';});
 const paper=await page.evaluate(()=>getComputedStyle(document.querySelector('.sb-paper')).backgroundColor);
 assert.notEqual(paper,'rgb(255, 254, 250)');
 passed.push('the evening theme recolors the note paper');

 assert.deepEqual(errors,[],'page errors: '+errors.join('; '));
 passed.push('no page JavaScript errors');
 await browser.close();
 console.log(passed.map(p=>'PASS '+p).join('\n'));
})().catch(e=>{console.error(e);process.exit(1);});
