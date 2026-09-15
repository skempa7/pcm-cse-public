// Additional regional variants: exercise actual selections and watch each
// sequence through completion, without using hidden state to complete it.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=process.env.CSE_TEST_OUTPUT||path.join(require('os').tmpdir(),'cse-animation-review');fs.mkdirSync(out,{recursive:true});
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});const results=[];try{
for(const region of ['hand-stiffness','shoulder-overuse','knee-injury']){
 const c=await b.newContext({viewport:{width:1280,height:800}}),p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto((process.env.CSE_TEST_URL||'http://127.0.0.1:8776/web/')+'#practice');await p.locator('#btnStart').waitFor({timeout:120000});await p.locator('[data-mode=coached]').click();await p.locator('[data-case="msk-'+region+'"]').click();await p.locator('#btnStart').click();await p.locator('#skipEntrance').click();await p.locator('#say').waitFor();
 await p.locator('[data-ew-tab=exam]').click();if(await p.locator('#ewExamAll').isVisible())await p.locator('#ewExamAll').click();await p.locator('#manSearch').fill('range of motion');await p.locator('[data-exam-action="msk_rom:complete"]').click();await p.locator('.exam-demo').waitFor();
 const stages=new Map();while(await p.locator('.exam-demo').count()){
  const f=await p.locator('.exam-demo').evaluate(e=>({stage:e.dataset.stage,elapsed:e.dataset.elapsed,caption:e.querySelector('.exam-demo-caption').textContent,svg:e.querySelector('svg').outerHTML})).catch(()=>null);
  if(f){if(!stages.has(f.stage))stages.set(f.stage,[]);stages.get(f.stage).push(f);}await p.waitForTimeout(250);
 }
 assert.equal(stages.size,4);assert.equal(await p.evaluate(()=>S.examination_activity.filter(e=>e.meta.status==='completed').length),1);assert.deepEqual(errors,[]);
 const records=[...stages.values()];results.push({region,stages:records.map(a=>({caption:a[0].caption,frames:a.length,variants:new Set(a.map(f=>f.svg)).size})),errors});
 fs.writeFileSync(out+'/regional-motion-'+region+'.json',JSON.stringify(records));await p.screenshot({path:out+'/final-regional-'+region+'.png'});
 await p.evaluate(rows=>{document.body.innerHTML='<main style="background:#fafbf5;color:#173d30">'+rows.map(row=>{const frames=[row[0],row[Math.floor(row.length/2)],row.at(-1)];return '<section style="display:grid;grid-template-columns:220px repeat(3,1fr);gap:12px"><p>'+row[0].caption+'</p>'+frames.map(f=>'<div><div class="exam-demo-canvas" style="height:220px">'+f.svg+'</div><p>'+f.elapsed+'s</p></div>').join('')+'</section>';}).join('')+'</main>';},records);await p.addStyleTag({path:path.resolve(__dirname,'../web/exam-animation.css')});await p.screenshot({path:out+'/motion-regional-'+region+'.png',fullPage:true});await c.close();
 console.log('Completed '+region+' through all four visible stages.');
}
fs.writeFileSync(out+'/regional-browser-results.json',JSON.stringify(results,null,2));
}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
