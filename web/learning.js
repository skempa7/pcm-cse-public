/* Evidence-bound learning UI. The server owns assistance, timing and repairs. */
(()=>{
  const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let current=null, learning=null, loading=false, selected='orient',lastEvidenceKey='',lobbyRequest=0;
  const request=async(path,body)=>{try{const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}catch(e){return {error:e.message};}};
  function lobby(){
    if(document.getElementById('learningLibrary'))return;
    const grid=document.getElementById('stationGrid');if(!grid)return;
    const progress=BOOT.progress||{};const cases=BOOT.cases||[];
    const skills=[...new Set(cases.flatMap(c=>c.skills||[]))].sort();
    const section=document.createElement('div');section.id='learningLibrary';section.className='learning-library';
    section.innerHTML=`<div class="coverage-strip"><strong>${cases.length} presentations</strong><span>${progress.variant_count||0} additional variations</span><span>${(progress.completed_cases||[]).length} presentations completed</span></div>
      <p class="small muted">Build a routine, then take it into an unfamiliar case. These authored teaching cases cover the four scheduled system blocks; supplementary presentations are labeled in the coverage inventory.</p>
      <div class="learning-filters"><label>Practice a skill<select id="skillFilter"><option value="">All skills</option>${skills.map(x=>`<option value="${E(x)}">${E(x.replaceAll('-',' '))}</option>`).join('')}</select></label>
      <label>Difficulty<select id="difficultyFilter"><option value="">All levels</option>${[...new Set(cases.map(c=>c.difficulty))].map(x=>`<option>${E(x)}</option>`).join('')}</select></label>
      <label>Experience<select id="experienceFilter"><option value="all">All presentations</option><option value="new">Not attempted yet</option><option value="weak">Related to previous weaknesses</option></select></label>
      <label>Case variation<select id="variantChoice"><option value="random">Mix coherent variations</option><option value="base">Base presentation</option></select><span id="variantNotice" class="tiny muted" role="status"></span></label></div>
      <p id="filterCount" class="small" role="status"></p>
      <details><summary>Learning progress and review status</summary><p>Completion, assistance and content review are separate measures.</p><div class="learning-metrics">${Object.entries(progress.completed_by_mode||{}).map(([k,v])=>`<span>${E(k)}: <b>${v}</b> completed</span>`).join('')||'<span>No completed attempts yet.</span>'}</div><p class="small">Suggested next level: <b>${E(progress.next_mode||'coached')}</b>. ${E(progress.fading_note||'Progress from guided to independent as your recall becomes reliable.')}</p><p class="small">Independent completions: ${progress.conditions?.independent||0}; assisted: ${progress.conditions?.assisted||0}; retries: ${progress.conditions?.branches||0}.</p><p class="small">Recurring needs: ${(progress.weaknesses||[]).map(x=>E(x.skill.replaceAll('-',' '))+' ('+x.attempts+' attempts)').join(', ')||'Complete and review several cases to establish a pattern.'}</p><p class="small">The library is source checked and structurally tested; no licensed-clinician approval is claimed. See Case review status and the delivered case inventory for review scope.</p></details>`;
    grid.before(section);
    const visible=()=>{
      const skill=document.getElementById('skillFilter').value, difficulty=document.getElementById('difficultyFilter').value, experience=document.getElementById('experienceFilter').value,system=document.getElementById('sysPick').value;
      return cases.filter(c=>(!skill||(c.skills||[]).includes(skill))&&(!difficulty||c.difficulty===difficulty)&&(!system||c.system===system)&&(experience!=='new'||!(progress.attempted_cases||[]).includes(c.id))&&(experience!=='weak'||(progress.weaknesses||[]).some(w=>(c.skills||[]).includes(w.skill))));
    };
    const filter=()=>{const ids=new Set(visible().map(c=>c.id));grid.querySelectorAll('[data-case]').forEach(card=>{card.hidden=!ids.has(card.dataset.case);if(card.hidden)card.querySelector('input').checked=false;});document.getElementById('filterCount').textContent=`${ids.size} matching presentations${!ids.size?' — broaden a filter or complete an attempt to establish weaknesses.':''}`;};
    section.querySelectorAll('select').forEach(x=>x.addEventListener('change',filter));document.getElementById('sysPick').addEventListener('change',filter);
    const refreshVariants=()=>{
      const id=grid.querySelector('input:checked')?.value,c=cases.find(c=>c.id===id),v=document.getElementById('variantChoice');
      const previous=v.value||'random',options=[{id:'random',label:'Mix coherent variations'},{id:'base',label:'Base presentation'},...(c?.variants||[])];
      v.innerHTML=options.map(x=>`<option value="${E(x.id)}">${E(x.label)}</option>`).join('');
      v.value=options.some(x=>x.id===previous)?previous:'base';
      document.getElementById('variantNotice').textContent=v.value!==previous?'This case is set to its base presentation. Choose another variation if you prefer.':'';
    };
    grid.addEventListener('change',refreshVariants);refreshVariants();
    const conceal=()=>{const exam=document.querySelector('input[name=uimode]:checked')?.value==='rehearsal';document.getElementById('variantChoice').closest('label').hidden=exam;};
    document.querySelectorAll('input[name=uimode]').forEach(x=>x.addEventListener('change',conceal));conceal();filter();
    document.getElementById('btnRandom').onclick=()=>{const pool=visible();if(!pool.length)return;const c=pool[Math.floor(Math.random()*pool.length)];const base=document.querySelector('input[name=uimode]:checked')?.value!=='rehearsal'&&document.getElementById('variantChoice').value==='base';window.pcmStart(false,{case_id:c.id,variant_id:base?'base':'random'});};
    document.getElementById('btnStart').onclick=()=>window.pcmStart(false,{variant_id:document.querySelector('input[name=uimode]:checked')?.value==='rehearsal'?'random':document.getElementById('variantChoice').value});
  }
  async function render(s){
    current=s;
    if(!s){
      learning=null;
      const requestId=++lobbyRequest,grid=document.getElementById('stationGrid');
      const latest=await request('/api/bootstrap');
      if(current||requestId!==lobbyRequest||!grid||document.getElementById('stationGrid')!==grid)return;
      if(!latest.error){BOOT.progress=latest.progress||{};BOOT.sessions=latest.sessions||[];window.pcmRefreshLobbyHistory?.();}
      lobby();
      if(latest.error){const count=document.getElementById('filterCount');if(count)count.textContent+=' · Showing last loaded progress; reconnect and return to refresh.';}
      return;
    }
    if(s.phase==='submitted'){await repairPanel(s);return;}
    if(!['guided','coached'].includes(s.learning_mode)||!['encounter','organize','note'].includes(s.phase))return;
    const data=await request(`/api/session/${s.id}/learning`);if(current?.id!==s.id||data.error||!data.available)return;
    learning=data;selected=data.selected;
    let panel=document.getElementById('encounterGuide');if(!panel){panel=document.createElement('section');panel.id='encounterGuide';panel.className='encounter-guide';const wrap=document.querySelector('#coachDock')||document.querySelector('#view .wrap-wide,#view .wrap-mid,#view .room-shell')||document.getElementById('view');wrap.prepend(panel);}
    panel.classList.toggle('coaching-open',s.learning_mode==='guided'&&s.phase==='encounter');
    panel.innerHTML=`<div class="guide-top"><div><span class="eyebrow">Your encounter compass</span><h2>Find your next step.</h2></div><span class="small">${E(data.timing)}</span><button class="btn sm ghost guide-expand" id="toggleGuide" aria-expanded="${s.learning_mode==='guided'&&s.phase==='encounter'}">Show approach</button><button class="btn primary" id="unstuckButton">Help me get unstuck</button></div><nav class="encounter-steps" aria-label="Mental sequence">${data.steps.map((x,i)=>`<button class="step-button ${x.id===selected?'active':''}" data-step="${E(x.id)}" aria-pressed="${x.id===selected}"><span>${i+1}</span>${E(x.label)}</button>`).join('')}</nav><div class="guide-purpose" id="guidePurpose"></div><div id="recoveryBody" aria-live="polite"></div><div id="guideApplication" aria-live="polite"></div><details class="reasoning-expand"><summary>See how questions change the next decision</summary><div class="reasoning-map">${(data.reasoning_map||[]).map(x=>`<article><h3>${E(x.question||x.label||'A discriminating question')}</h3><p>${E(x.why||'')}</p><div class="decision-fork"><div><b>If present</b><p>${E(x.if_present||'Consider how this changes urgency.')}</p></div><div><b>If absent</b><p>${E(x.if_absent||'Reconsider likelihood; absence alone may not exclude disease.')}</p></div></div><p>${E(x.next_action||'')}</p><p class="small">Document: ${E(x.document||'Only the answer you actually obtained.')}</p></article>`).join('')||'<p>Complaint → working possibilities → a discriminating question → a relevant examination → interpretation → explanation → evidence-supported SOAP.</p>'}</div></details>`;
    document.getElementById('toggleGuide').onclick=e=>{const opened=panel.classList.toggle('coaching-open');e.currentTarget.setAttribute('aria-expanded',String(opened));e.currentTarget.textContent=opened?'Hide approach':'Show approach';};
    const purpose=()=>{const st=data.steps.find(x=>x.id===selected);document.getElementById('guidePurpose').textContent=st?.purpose||'';};purpose();
    panel.querySelectorAll('[data-step]').forEach(b=>b.onclick=async()=>{selected=b.dataset.step;await request(`/api/session/${s.id}/stage`,{step:selected});panel.querySelectorAll('[data-step]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});document.getElementById('recoveryBody').innerHTML='';purpose();});
    document.getElementById('unstuckButton').onclick=()=>showHint(s);
    if(s.learning_mode==='guided'&&s.phase==='encounter'){
      const exercise=document.createElement('details');exercise.className='guided-first';exercise.innerHTML='<summary>Practice the first move</summary><p>You have introduced yourself. Before narrowing to yes/no questions, which move helps you build a shared agenda?</p><div class="choice-row"><button class="btn" data-first="0">Start listing diagnoses.</button><button class="btn" data-first="1">Invite the patient’s story.</button><button class="btn" data-first="2">Skip to examination.</button></div><p class="first-result" role="status"></p>';
      panel.append(exercise);exercise.querySelectorAll('[data-first]').forEach(b=>b.onclick=()=>{exercise.querySelector('.first-result').textContent=b.dataset.first==='1'?'Yes. Now ask an open invitation in your own words, listen, then clarify one detail.':'Pause and recall the purpose: understand their concern before narrowing the story. Try again.';});
    }
  }
  async function showHint(s){
    const result=await request(`/api/session/${s.id}/hint`,{});const body=document.getElementById('recoveryBody');if(!body||current?.id!==s.id)return;
    if(result.step)selected=result.step;
    if(result.error||result.wait){body.textContent=result.error||result.text;return;}
    body.innerHTML=`<div class="recovery-card"><div class="recovery-routine">${result.routine.map((x,i)=>`<span><b>${i+1}</b>${E(x)}</span>`).join('')}</div><div class="recovery-columns"><div><span class="eyebrow">Cue ${result.level} of 3</span><h3>${E(result.text)}</h3><p>Think for a moment. Choose one question or action yourself.</p>${result.level<3?'<button class="btn" id="moreHint" disabled>Stronger cue in 5 seconds</button>':'<p class="small">Now apply the principle using your own words.</p>'}${result.question?'<button class="btn ghost" id="tryCue">Put this question in my draft</button>':''}</div><details><summary>What you have actually obtained</summary>${result.obtained.map(e=>`<p class="evidence-quote"><span>#${e.seq}</span> ${E(e.text)}</p>`).join('')||'<p>No patient disclosures or completed examinations yet. Begin with the complaint.</p>'}</details></div></div>`;
    const more=document.getElementById('moreHint');if(more){setTimeout(()=>{if(more.isConnected){more.disabled=false;more.textContent='Give me a stronger cue';}},5100);more.onclick=()=>showHint(s);}
    document.getElementById('tryCue')?.addEventListener('click',()=>{const input=document.getElementById('say')||document.querySelector('.composer textarea');if(input){input.value=result.question;input.focus();input.dispatchEvent(new Event('input',{bubbles:true}));}else body.insertAdjacentHTML('beforeend','<p>Apply the question in your own words in the encounter or note.</p>');});
  }
  async function repairPanel(s){
    if(document.getElementById('repairPractice'))return;
    const item=await request(`/api/session/${s.id}/repair`); const support=await request(`/api/session/${s.id}/learning`);if(item.error||current?.id!==s.id||document.getElementById('repairPractice'))return;
    const panel=document.createElement('section');panel.id='repairPractice';panel.className='repair-practice card';
    panel.innerHTML=`<span class="eyebrow">${item.requires_current_review?'Historical feedback':'A short repair before your next case'}</span><p class="small">${E(s.learning_mode)} · ${support.summary?.hints_used||0} hints · ${support.summary?.assisted?'assisted performance':'unassisted performance'}${s.branch?.is_branch?' · separate retry branch':''}</p><h2>${E(item.title)}</h2><p>${E(item.stem)}</p><div class="repair-choices">${item.choices.map((c,i)=>`<button class="btn" data-choice="${i}">${E(c)}</button>`).join('')}</div><div class="repair-result" role="status"></div><p class="small">Your original note and score remain locked. Repair attempts are tracked separately.</p>`;
    (document.querySelector('#view .wrap-wide,#view .wrap-mid')||document.getElementById('view')).prepend(panel);
    panel.querySelectorAll('[data-choice]').forEach(b=>b.onclick=async()=>{const r=await request(`/api/session/${s.id}/repair`,{id:item.id,choice:Number(b.dataset.choice)});panel.querySelector('.repair-result').innerHTML=`<h3>${r.error?E(r.error):r.correct?'That is supported.':'Try the evidence rule again.'}</h3><p>${E(r.explanation||'')}</p>${r.correct?`<p>${E(r.retry_prompt)}</p><div class="choice-row">${(r.recommended_cases||[]).map(id=>`<button class="btn" data-transfer="${E(id)}">Apply in ${E((BOOT.cases||[]).find(c=>c.id===id)?.title||'another case')}</button>`).join('')}</div>`:''}`;panel.querySelectorAll('[data-transfer]').forEach(x=>x.onclick=()=>window.pcmStart(false,{case_id:x.dataset.transfer,learning_mode:'coached',variant_id:'random'}));});
  }
  function showApplication(data,s){
    const host=document.getElementById('guideApplication');if(!host)return;
    const application=data.application;if(!application){host.innerHTML='';return;}
    const item=application.transfer,key=item?.id||'completed';if(host.dataset.item===key)return;
    host.dataset.item=key;
    host.innerHTML=`<div class="recovery-card"><p>${E(application.text)}</p>${item?`<h3>Transfer: a different situation</h3><p>${E(item.stem)}</p><div class="choice-row">${item.choices.map((c,i)=>`<button class="btn" data-apply="${i}">${E(c)}</button>`).join('')}</div><p class="transfer-result" role="status"></p>`:''}</div>`;
    host.querySelectorAll('[data-apply]').forEach(b=>b.onclick=async()=>{const r=await request(`/api/session/${s.id}/transfer`,{id:item.id,choice:Number(b.dataset.apply)});host.querySelector('.transfer-result').textContent=r.error||(r.correct?'Yes. ':'Reconsider. ')+(r.explanation||'')+' '+(r.next||'');if(r.correct)host.querySelectorAll('[data-apply]').forEach(x=>x.disabled=true);});
  }
  async function syncGuide(s){
    current=s;if(!s||!['guided','coached'].includes(s.learning_mode)||s.phase==='submitted')return;
    const key=s.id+':'+s.phase+':'+(s.transcript||[]).map(x=>x.seq).join(',');
    if(key===lastEvidenceKey||loading)return;lastEvidenceKey=key;loading=true;
    const data=await request(`/api/session/${s.id}/learning`);loading=false;
    if(current?.id!==s.id||data.error||!data.available)return;
    const previousStep=selected;learning=data;selected=data.selected;
    if(previousStep!==selected){const old=document.getElementById('recoveryBody');if(old)old.innerHTML='';}
    const panel=document.getElementById('encounterGuide');if(!panel)return;
    panel.querySelectorAll('[data-step]').forEach(b=>{b.classList.toggle('active',b.dataset.step===selected);b.setAttribute('aria-pressed',String(b.dataset.step===selected));});
    const purpose=document.getElementById('guidePurpose');if(purpose)purpose.textContent=data.steps.find(x=>x.id===selected)?.purpose||'';
    showApplication(data,s);
  }
  window.pcmLearningRender=s=>{lastEvidenceKey='';render(s);};
  window.pcmLearningState=s=>{syncGuide(s);};
})();
