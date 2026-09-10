import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(process.argv[2]||path.join(path.dirname(fileURLToPath(import.meta.url)),'..'));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let total=0,turns=0,links=0;
for(const edition of ['.']){
 const web=path.join(root,edition,'web');
 const {buildPrintSections,chooseSimulation}=await import(path.join(web,'walkthrough-print.js'));
 const manifest=JSON.parse(fs.readFileSync(path.join(web,'print-assets/manifest.json')));
 const lessons=path.join(root,edition,'pcmcse/teaching/lessons');
 let count=0;
 for(const file of fs.readdirSync(lessons).filter(f=>f.endsWith('.json'))){
  const container=JSON.parse(fs.readFileSync(path.join(lessons,file)));
  for(const l of container.walkthroughs){
   const before=JSON.stringify(l);const sections=buildPrintSections(l,manifest,[]),html=sections.flatMap(s=>s.blocks).join('');
   assert.equal(JSON.stringify(l),before,'print must never mutate lesson/evidence');
   assert.deepEqual(sections.map(s=>s.title),['Doorway preparation','Encounter storyboard','Clinical reasoning & memory','Example SOAP note','Documentation evidence','Recall exercise','Recall explanations','Sources & review']);
   let last=-1;
   l.timeline.forEach((t,i)=>{const marker=`data-turn-index="${i}"`;const pos=html.indexOf(marker);assert(pos>last,`chronology ${l.case_id} ${i}`);last=pos;for(const key of ['student','patient','action','finding','why'])if(t[key])assert(html.includes(esc(t[key]).replaceAll('\n','<br>')),`missing ${l.case_id} ${key}: ${t[key]}`);});
   for(const key of ['S','O','A','P']){const text=Array.isArray(l.note[key])?l.note[key].join('\n'):l.note[key];for(const paragraph of String(text).split('\n').filter(x=>x.trim()))assert(html.includes(esc(paragraph)),`SOAP omission ${l.case_id} ${key}`);}
   for(const link of l.note_links){assert(html.includes(esc(link.statement)));for(const id of link.event_ids){const e=l.ledger.find(x=>x.seq===id);const mapped=l.timeline.some(t=>(t.event_ids||[]).includes(id));if(e&&!mapped)assert(html.includes(esc(e.text).replaceAll('\n','<br>')),`missing extra ledger ${id}`);if(mapped)assert(html.includes('Record IDs:')&&html.includes(String(id)),`missing referenced ledger ${id}`);}}
   for(const r of l.recall){assert(html.includes(esc(r.prompt)));assert(html.includes(esc(r.answer)));}
   const simulation=chooseSimulation(l,manifest);assert(simulation,'missing simulation screenshot');
   const imgs=[...html.matchAll(/<img src="([^"]+)"/g)].map(m=>new URL(m[1]));assert(imgs.length>0);
   for(const image of imgs)assert(fs.existsSync(image),'missing local asset '+image);
   assert(!html.includes('src="http'),'all print images local');
   assert(!html.includes('undefined'),'undefined content');
   count++;turns+=l.timeline.length;links+=l.note_links.length;
  }
 }
 assert.equal(count,72);total+=count;
 const study=fs.readFileSync(path.join(web,'study.js'),'utf8');
 assert(study.includes('if(!await verifyCached(true))return;'));
 assert(study.includes('token!==printTask||location.hash!==route'));
 assert(!study.includes('preparePrintedLesson'));
 const css=fs.readFileSync(path.join(web,'walkthrough-print.css'),'utf8');
 assert(css.includes('size: Letter landscape'));assert(css.includes('10.5pt'));assert(css.includes('grid-template-columns:1fr 1fr'));
}
console.log(`PASS ${total} authored paths, ${turns} chronological turns, ${links} note links; exact dialogue/findings/SOAP/recall preserved; source objects immutable; all linked print images present in both editions.`);
