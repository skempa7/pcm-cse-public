const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),assert=require('assert/strict');
const base=process.env.CSE_TEST_URL||'http://127.0.0.1:8775/web/',out=process.env.CSE_TEST_OUTPUT||require('os').tmpdir()+'/cse-note-consistency';fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const ctx=await browser.newContext({viewport:{width:1440,height:900}}),p=await ctx.newPage();const checks=[];
for(const [cid,expected,hasGap] of [['gi-diarrhea-dehydration',2,true],['renal-acute-retention',3,true],['cardio-febrile-cough',3,false],['msk-knee-injury',3,false]]){
 await p.goto(base+'#cases/'+cid);await p.locator('#material-soap').waitFor({timeout:120000});await p.locator('#material-soap').click();await p.waitForFunction(()=>document.body.hasAttribute('data-walkthrough-preview'));
 const diagnoses=await p.locator('.rp-note-assessment h3').allTextContents(),limits=await p.locator('.rp-key-limit').allTextContents();assert.equal(diagnoses.length,expected);assert.equal(limits.length>0,hasGap);
 await p.locator('#pwClosePrint').click();await p.locator('.material-details summary').click();await p.locator('.material-details a').click();await p.locator('[data-section=soap]').click();await p.locator('#lesson-soap .example-note').waitFor();
 const online=await p.locator('#lesson-soap .example-note').innerText();for(const d of diagnoses)assert(online.includes(d),cid+' diverged diagnosis');assert.deepEqual(await p.locator('#lesson-soap .clinical-key-limit').allTextContents(),limits,cid+' inconsistent warning');
 if(cid==='gi-diarrhea-dehydration')assert(!online.includes('Medication-associated'));
 if(cid==='cardio-febrile-cough'){assert.match(online,/Amoxicillin.*hives/i);assert.match(online,/roommate/);assert(!online.includes('No known drug allergies'));}
 checks.push({cid,diagnoses:expected,gap:hasGap});
}
await browser.close();fs.writeFileSync(out+'/example-consistency.json',JSON.stringify({result:'PASS',checks},null,2));console.log('PASS online and printed example content/category warnings agree across new, revised and authoring-gap cases');})().catch(e=>{console.error(e);process.exit(1)});
