/* Current five-section print renderer, not the superseded transcript edition. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const root=path.resolve(process.argv[2]||path.join(import.meta.dirname,'..'));
const {buildPartnerSections,PRINT_EDITIONS}=await import(path.join(root,'web/partner-print.js'));
const lessons=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-c',`import json\nfrom pcmcse import cases,teaching\nprint(json.dumps([teaching.read(cid,vid) for cid,c in cases.all_cases().items() for vid in ['base']+[v['id'] for v in c.get('variants',[])]]))`],{cwd:root,maxBuffer:64*1024*1024}));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
assert.equal(lessons.length,82);assert.equal(new Set(lessons.map(l=>l.case_id)).size,34);
assert.deepEqual(Object.keys(PRINT_EDITIONS),['doorway','patient','examiner','blank','soap','student','study']);
let replies=0,findings=0;
for(const l of lessons){const before=JSON.stringify(l);
 for(const edition of Object.keys(PRINT_EDITIONS)){
  const sections=buildPartnerSections(l,edition),html=sections.flatMap(s=>s.blocks).join('');
  assert(!html.includes('undefined')&&!html.includes('[object Object]'),l.case_id+' invalid data');
  assert(!html.includes('data-turn-index'),l.case_id+' old transcript unexpectedly printed');
  if(['patient','study'].includes(edition)){
   for(const section of l.partner_script.sections)for(const t of section.topics)for(const a of [t.answer,...t.followups.map(f=>f.answer)]){assert(html.includes(esc(a).replaceAll('\n','<br>')),l.case_id+' missing answer '+a);replies++;}
   const patient=sections.find(s=>s.kind==='patient').blocks.join('');
   const headings=[...patient.matchAll(/<h2>(.*?)<\/h2>/g)].map(x=>x[1]);
   assert.deepEqual(headings.slice(0,9),['Opening complaint','History of present illness','Surgical history','Medications','Allergies and reactions','Social history','Family history','Past medical history','Review of systems']);
   assert(!patient.includes('What the student might ask')&&!patient.includes('What the patient should say'));
  }
  if(['examiner','study'].includes(edition))for(const t of l.partner_examinations){assert(html.includes(esc(t.finding).replaceAll('\n','<br>')),l.case_id+' missing finding');findings++;}
  if(['soap','study'].includes(edition)){for(const group of ['subjective','objective'])for(const row of l.partner_note[group])for(const p of row.text.split('\n\n'))assert(html.includes(esc(p).replaceAll('\n','<br>')),l.case_id+' note omission');for(const row of [...l.partner_note.assessment,...l.partner_note.plan])assert(html.includes(esc(row.text).replaceAll('\n','<br>')),l.case_id+' reasoning/plan omission');}
  if(!PRINT_EDITIONS[edition].protected){assert(!html.includes('rp-topic-label'));assert(!html.includes('rp-finding'));assert(!html.includes('rp-note-assessment'));}
  if(edition==='study')assert.deepEqual(sections.map(s=>s.title),['Doorway information','Patient script','Examinations and findings','Blank SOAP workspace','Blank SOAP workspace','Example SOAP note']);
  if(edition==='blank'){assert.equal(sections.length,2);assert.equal((html.match(/class="rp-writing"/g)||[]).length,4);}
  assert.equal(JSON.stringify(l),before,'render mutated source '+l.case_id);
 }
}
assert.throws(()=>buildPartnerSections(lessons[0],'unknown'),/Choose a printable/);
console.log(JSON.stringify({result:'PASS',paths:82,editions:7,patientResponsesChecked:replies,examinationFindingsChecked:findings,limits:'Content inclusion, section order, safe edition separation and immutability; PDF geometry and clinical validation run separately.'}));
