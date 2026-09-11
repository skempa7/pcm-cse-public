/* Evidence-bound learning UI. The server owns assistance, timing and repairs. */
(()=>{
  const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let current=null, learning=null, loading=false, selected='orient',lastEvidenceKey='',lobbyRequest=0;
  if(!document.getElementById('caseGuideStyles')){const style=document.createElement('link');style.id='caseGuideStyles';style.rel='stylesheet';style.href=new URL('./guided.css?v=portal-1',location.href).href;document.head.append(style);}
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
    const conceal=()=>{const mode=typeof currentUiMode==='function'?currentUiMode():document.querySelector('input[name=uimode]:checked')?.value;const reveal=typeof MODES!=='undefined'?!!MODES[mode]?.reveal:['guided','coached'].includes(mode);document.getElementById('variantChoice').closest('label').hidden=!reveal;window.pcmPortal?.decoratePractice(mode,reveal);};
    document.querySelectorAll('input[name=uimode]').forEach(x=>x.addEventListener('change',conceal));conceal();filter();
    document.getElementById('btnRandom').onclick=()=>{const pool=visible();if(!pool.length)return;const c=pool[Math.floor(Math.random()*pool.length)];const base=document.querySelector('input[name=uimode]:checked')?.value!=='rehearsal'&&document.getElementById('variantChoice').value==='base';window.pcmStart(false,{case_id:c.id,variant_id:base?'base':'random'});};
    document.getElementById('btnStart').onclick=()=>window.pcmStart(false,{variant_id:['independent','rehearsal'].includes(document.querySelector('input[name=uimode]:checked')?.value)?'random':document.getElementById('variantChoice').value});
    if(typeof currentUiMode==='function'&&typeof MODES!=='undefined')window.pcmPortal?.decoratePractice(currentUiMode(),MODES[currentUiMode()]?.reveal);
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
    if(s.learning_mode==='guided'&&data.case_guide){renderCaseGuide(s,data);return;}
    let panel=document.getElementById('encounterGuide');if(!panel){panel=document.createElement('section');panel.id='encounterGuide';panel.className='encounter-guide';const wrap=document.querySelector('#coachDock')||document.querySelector('#view .wrap-wide,#view .wrap-mid,#view .room-shell')||document.getElementById('view');wrap.prepend(panel);}
    panel.classList.toggle('coaching-open',s.learning_mode==='guided'&&s.phase==='encounter');
    panel.classList.toggle('coach-aside',s.phase!=='encounter');
    panel.innerHTML=`<div class="guide-top"><div><span class="eyebrow">${E(data.timing)}</span></div><button class="btn sm ghost guide-expand" id="toggleGuide" aria-expanded="${s.learning_mode==='guided'&&s.phase==='encounter'}">Show approach</button><button class="btn sm ghost" id="unstuckButton">I'm stuck</button></div><nav class="encounter-steps" aria-label="Mental sequence">${data.steps.map((x,i)=>`<button class="step-button ${x.id===selected?'active':''}" data-step="${E(x.id)}" aria-pressed="${x.id===selected}"><span>${i+1}</span>${E(x.label)}</button>`).join('')}</nav><div class="guide-purpose" id="guidePurpose"></div><div id="recoveryBody" aria-live="polite"></div><div id="guideApplication" aria-live="polite"></div><details class="reasoning-expand"><summary>See how questions change the next decision</summary><div class="reasoning-map">${(data.reasoning_map||[]).map(x=>`<article><h3>${E(x.question||x.label||'A discriminating question')}</h3><p>${E(x.why||'')}</p><div class="decision-fork"><div><b>If present</b><p>${E(x.if_present||'Consider how this changes urgency.')}</p></div><div><b>If absent</b><p>${E(x.if_absent||'Reconsider likelihood; absence alone may not exclude disease.')}</p></div></div><p>${E(x.next_action||'')}</p><p class="small">Document: ${E(x.document||'Only the answer you actually obtained.')}</p></article>`).join('')||'<p>Complaint → working possibilities → a discriminating question → a relevant examination → interpretation → explanation → evidence-supported SOAP.</p>'}</div></details>`;
    document.getElementById('toggleGuide').onclick=e=>{const opened=panel.classList.toggle('coaching-open');e.currentTarget.setAttribute('aria-expanded',String(opened));e.currentTarget.textContent=opened?'Hide approach':'Show approach';};
    const purpose=()=>paintPurpose(data,s,selected);purpose();
    panel.querySelectorAll('[data-step]').forEach(b=>b.onclick=async()=>{selected=b.dataset.step;await request(`/api/session/${s.id}/stage`,{step:selected});document.querySelectorAll('[data-step]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});document.getElementById('recoveryBody').innerHTML='';purpose();
      // The move is derived server-side from the stage the student is in, and
      // the refresh is keyed on the transcript -- so without this the choice
      // changed nothing until the patient next spoke.
      lastEvidenceKey='';syncGuide(current||s);const history=data.hint_history?.[selected];if(history?.unlocked)drawHint(s,{...history.cues[history.unlocked-1],unlocked:history.unlocked,wait_ms:history.wait_ms,replay:true});});
    document.getElementById('unstuckButton').onclick=()=>showHint(s);
    if(s.learning_mode==='guided'&&s.phase==='encounter'){
      const exercise=document.createElement('details');exercise.className='guided-first';exercise.innerHTML='<summary>Practice the first move</summary><p>You have introduced yourself. Before narrowing to yes/no questions, which move helps you build a shared agenda?</p><div class="choice-row"><button class="btn" data-first="0">Start listing diagnoses.</button><button class="btn" data-first="1">Invite the patient’s story.</button><button class="btn" data-first="2">Skip to examination.</button></div><p class="first-result" role="status"></p>';
      panel.append(exercise);exercise.querySelectorAll('[data-first]').forEach(b=>b.onclick=()=>{exercise.querySelector('.first-result').textContent=b.dataset.first==='1'?'Yes. Now ask an open invitation in your own words, listen, then clarify one detail.':'Pause and recall the purpose: understand their concern before narrowing the story. Try again.';});
    }
  }
  function draftQuestion(question,host){
    const input=document.getElementById('say')||document.querySelector('.composer textarea');
    if(!input){host?.insertAdjacentHTML('beforeend','<p role="status">Return to the encounter composer to practice this line.</p>');return;}
    if(input.value.trim()&&input.value.trim()!==question.trim()&&!window.confirm('Replace your unsent question with this practice draft?'))return;
    input.value=question;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
    const status=host?.querySelector('[data-guide-message]');if(status)status.textContent='Draft ready. Review or edit it, then send it to the patient.';
  }
  const mentalStep=group=>({connect:'orient',opening:'orient',pattern:'pattern',discriminate:'discriminate',background:'discriminate',context:'discriminate',perspective:'discriminate',ros:'discriminate',prepare:'examine',examine:'examine',close:'close',document:'document'}[group]||'orient');
  function coverageHtml(coverage){
    return `<p class="small">${E(coverage.note)}</p><div class="guide-evidence-grid"><div><h4>Subjective foundations</h4>${coverage.history.map(x=>`<p><span class="guide-evidence-status ${x.obtained?'obtained':''}">${x.obtained?'Obtained':'Review'}</span> ${E(x.label)}</p>`).join('')}<h4>Relevant ROS topics obtained</h4>${coverage.ros.map(x=>`<p><b>${E(x.system)}</b> ${x.obtained}/${x.target} ${x.topics.length?'· '+E(x.topics.join(', ')):''}</p>`).join('')}</div><div><h4>Objective evidence</h4>${coverage.objective.map(x=>`<p><span class="guide-evidence-status ${x.obtained?'obtained':''}">${x.obtained?'Obtained':'Review'}</span> ${E(x.label)}</p>`).join('')}</div></div>`;
  }
  // A focus dropdown and a line of general advice is not a next step. When the
  // server supplies the single next move, lead with it: what to do, the words
  // that do it, and why -- the reason last and small, because the action is
  // the point. Both the full render and the lightweight refresh call this, or
  // the refresh overwrites the move with the stage blurb again.
  function paintPurpose(data,s,selected){
    const host=document.getElementById('guidePurpose');if(!host)return;
    const move=data.next_action;
    if(move&&move.title){
      // 41 of the 47 question tasks carry the same string as title AND
      // question, so the panel printed the sentence twice -- "Next When did
      // your symptoms first begin? / Ask "When did your symptoms first begin?"".
      // The guided card already avoids this; do the same here.
      // One move, said once. The panel used to print a heading, a NEXT line,
      // an ASK line, a reason paragraph, a gaps line and a footer -- six
      // blocks for one suggestion, with the reason as large as the question.
      // Now: what to do, in the words to say it, then the actions. The reason
      // is one line away for anyone who wants it.
      // A label earns its line only when it says something the move line does
      // not. With no question the title IS the move, so printing it as both a
      // heading and the move said "Auscultate abdomen" twice.
      const label=(move.question&&move.title&&move.title!==move.question)?move.title:'';
      const lead=move.question?`\u201c${E(move.question)}\u201d`:E(move.title);
      const showProgress=move.group_total>1&&Number.isFinite(move.group_done);
      host.innerHTML=`<div class="coach-next">`
        +(label?`<p class="coach-label">${E(label)}</p>`:'')
        +`<p class="coach-move${move.question?' is-quote':''}">${lead}</p>`
        +`<div class="coach-actions">`
        +`${move.question&&s.phase==='encounter'?'<button class="btn sm" id="coachDraft">Draft question</button>':''}`
        +`</div>`
        +(((move.gaps&&move.gaps.length)||showProgress)?`<p class="coach-meta">`
            +(showProgress?`<span class="coach-progress">${E(move.group_label||'This phase')} \u00b7 ${move.group_done} of ${move.group_total}</span>`:'')
            +((move.gaps&&move.gaps.length)?`<span class="coach-gaps">${s.phase==='encounter'?'Still to establish':'Your record has nothing for'}: ${E(move.gaps.join(', '))}</span>`:'')
          +`</p>`:'')
        +((move.why||'').trim()?`<details class="coach-why"><summary>Why this</summary><p>${E(move.why)}</p></details>`:'')
        +`</div>`;
      const actions=host.querySelector('.coach-actions');
      if(actions){
        const add=(label,primary,fn)=>{const b=document.createElement('button');b.type='button';
          b.className='btn sm'+(primary?'':' ghost');b.textContent=label;b.onclick=fn;actions.append(b);return b;};
        // An examination move cannot be drafted into the composer; the useful
        // action is to open the panel that performs it.
        if(!move.question&&move.kind==='exam'&&s.phase==='encounter'){
          add('Open Examine',true,()=>document.querySelector('[data-ew-tab=exam]')?.click());
        }
        // Choosing a different move opens the stage list in a sheet, where each
        // one names itself -- and the move you were reading is still here when
        // you come back, which the old dropdown could not promise.
        const steps=document.querySelector('#encounterGuide .encounter-steps');
        if(steps&&window.pcmSheet)add('Work on something else',false,()=>{
          steps.hidden=false;
          // The list is the seven parts of an encounter, not seven alternative
          // questions. Labelling it "other moves" promised something it never
          // contained, and picking one appeared to do nothing at all.
          let note=document.getElementById('coachStageNote');
          if(!note){note=document.createElement('p');note.id='coachStageNote';note.className='coach-stage-note';
            note.textContent='Pick the part you are actually working on. Your coach suggests its next move from there. Nothing is said to the patient and nothing is recorded in your encounter.';}
          window.pcmSheet('Which part of the encounter are you working on?',[note,steps]);
        });
        // The workspace hides #recoveryBody, so calling showHint() alone spent
        // a recorded assistance count and displayed nothing at all. Show the
        // cue where the student is looking.
        add("I'm stuck",false,async()=>{
          await showHint(s);
          const body=document.getElementById('recoveryBody');
          if(body&&window.pcmSheet&&!document.querySelector('dialog.ew-sheet'))
            window.pcmSheet('Get unstuck \u00b7 pause, orient, choose',[body]);
        });
        // The shell keeps its own copies so their handlers stay wired, but two
        // "I'm stuck" buttons on one card is one too many. Hide them wherever
        // this row has rendered; the row is the single place to act.
        ['unstuckButton','toggleGuide'].forEach(id=>document.getElementById(id)?.classList.add('coach-shell-ctl'));
      }
      const draft=document.getElementById('coachDraft');
      if(draft)draft.onclick=()=>{
        // Drafting fills the box and stops. It never sends, never scores, and
        // never overwrites something the student has already typed.
        const box=document.getElementById('say');if(!box)return;
        const existing=box.value.trim();
        if(existing&&existing!==move.question){
          // Something is already typed. Silently focusing the box looked like a
          // dead button; silently replacing would lose the student's words.
          const row=document.querySelector('.coach-actions');if(!row)return;
          if(document.getElementById('coachDraftReplace')){box.focus();return;}
          const ask=document.createElement('span');ask.className='coach-conflict';
          ask.innerHTML='You have an unsent message. <button type="button" class="btn sm ghost" id="coachDraftReplace">Replace it</button> <button type="button" class="btn sm ghost" id="coachDraftKeep">Keep mine</button>';
          row.append(ask);
          ask.querySelector('#coachDraftReplace').onclick=()=>{box.value=move.question;box.dispatchEvent(new Event('input',{bubbles:true}));ask.remove();box.focus();};
          ask.querySelector('#coachDraftKeep').onclick=()=>{ask.remove();box.focus();};
          return;
        }
        box.value=move.question;box.dispatchEvent(new Event('input',{bubbles:true}));box.focus();
      };
      return;
    }
    host.textContent=(data.steps||[]).find(x=>x.id===selected)?.purpose||'';
  }

  /* Guided mode rebuilds this whole card on every patient reply. That threw
     away keyboard focus (Tab restarted at the top of the document) and closed
     any disclosure the student had opened. Carry both across the rebuild. */
  function keepPlace(panel,paint){
    const before=document.activeElement;
    const focusKey=panel&&panel.contains(before)?(before.id||before.textContent.trim()):null;
    const open=panel?[...panel.querySelectorAll('details[open] > summary')].map(x=>x.textContent.trim()):[];
    paint();
    const after=document.getElementById('encounterGuide');if(!after)return;
    open.forEach(label=>{const sum=[...after.querySelectorAll('details > summary')].find(x=>x.textContent.trim()===label);
      if(sum)sum.parentElement.open=true;});
    if(!focusKey)return;
    // The workspace re-parents this card's children into its own scroll and
    // footer AFTER the paint, and re-parenting blurs. Put the keyboard back
    // once everything has finished moving, and only if nothing else took it.
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      const now=document.activeElement;
      if(now&&now!==document.body&&!after.contains(now))return;   // user moved on
      const host=document.getElementById('encounterGuide')||after;
      const target=document.getElementById(focusKey)
        ||[...host.querySelectorAll('button,a[href],summary,select')].find(x=>x.textContent.trim()===focusKey);
      target?.focus({preventScroll:true});
    }));
  }
  function renderCaseGuide(s,data){
    const panelBefore=document.getElementById('encounterGuide');
    if(panelBefore&&panelBefore.classList.contains('case-guide'))
      return keepPlace(panelBefore,()=>renderCaseGuideInner(s,data));
    return renderCaseGuideInner(s,data);
  }
  function renderCaseGuideInner(s,data){
    const guide=data.case_guide;if(!guide)return;
    let panel=document.getElementById('encounterGuide');
    if(!panel){panel=document.createElement('section');panel.id='encounterGuide';} const guideHost=s.phase==='encounter'?document.querySelector('#view .convo'):null; if(guideHost){guideHost.prepend(panel);}else if(!panel.isConnected){(document.getElementById('coachDock')||document.getElementById('view')).prepend(panel);}
    panel.className='encounter-guide case-guide coaching-open';
    const active=guide.tasks.find(t=>t.id===guide.selected)||guide.tasks[0],index=guide.tasks.indexOf(active),group=guide.groups.find(g=>g.id===active.group);
    selected=mentalStep(active.group);
    const sameGroup=guide.tasks.filter(t=>t.group===active.group),groupIndex=sameGroup.indexOf(active)+1;
    const ready=active.status==='obtained',deferred=active.status==='deferred';
    panel.innerHTML=`<div class="case-guide-top"><div><span class="eyebrow">Guided encounter · ${E(guide.variant_label)}</span><h2>${E(group?.label||'Your next move')}</h2></div><span class="guide-position">${groupIndex}/${sameGroup.length} in this phase</span></div>
      <div class="guide-case-context"><b>${E(guide.title)}</b><span>${E(data.timing)}</span></div>
      ${guide.urgent?`<details class="guide-urgency"><summary>Prioritize urgent care when needed</summary><p>${E(guide.notice)} Continue nonurgent practice only while care permits; do not delay escalation to finish a checklist.</p></details>`:''}
      <article class="guide-current" aria-live="polite"><div class="guide-current-label"><span>${ready?'✓ Evidence recorded':deferred?'Deferred · no credit':active.status==='review'?'Coverage checkpoint · review':'Your next move'}</span><span>One step at a time</span></div>
      <h3>${E(active.kind==='question'&&active.title===active.question?'Ask, listen, then follow the answer':active.title)}</h3>
      ${active.question?`<blockquote>${E(active.question)}</blockquote>`:''}
      <p class="guide-why"><b>Why:</b> ${E(active.why)}</p>
      ${active.kind==='exam'?`<div class="guide-technique"><b>Sites and technique to consider</b><p>${E((active.components||[]).join(' · ')||'General observation')}</p>${active.technique?`<details><summary>Technique note</summary><p>${E(active.technique)}</p></details>`:''}<p class="small">${active.focused_subset?'This path selects the authored key special test. Additional tests remain available when indicated.':'A focused selection from this case’s written example; other catalog actions remain available when indicated.'} Select the appropriate components yourself. No result is supplied until the examination finishes.</p></div>`:''}
      ${active.kind==='checkpoint'?coverageHtml(guide.coverage):''}${active.kind==='decision'?`<p class="small">${E(active.decision_note)}</p>`:''}
      ${active.evidence_ids?.length?`<p class="guide-sources">Evidence: ${active.evidence_ids.map(n=>'#'+n).join(', ')}. ${active.kind==='question'?'The spoken reply remains in your encounter record.':''}</p>`:''}
      <div class="guide-actions">${active.question&&s.phase==='encounter'?'<button class="btn primary" id="guideDraft">Draft this question</button>':''}${active.kind==='exam'&&s.phase==='encounter'?'<button class="btn primary" id="guideOpenExam">Open this examination</button>':''}${active.kind==='document'&&s.phase==='encounter'?'<button class="btn primary" id="guideFinish">Go to Finish encounter</button>':''}${active.kind==='decision'?'<button class="btn primary" id="guideChart">Review doorway &amp; vitals</button><button class="btn" id="guideDecisionContinue">Continue focused history</button>':''}<button class="btn ghost" id="unstuckButton">Help me get unstuck</button></div><p class="small guide-message" data-guide-message role="status">${ready?'You can revisit this step or move on.':deferred?'This step was deferred. It remains absent from your evidence until actually obtained.':''}</p>
      </article><div class="guide-navigation"><button class="btn sm" id="guidePrevious" ${index===0?'disabled':''}>← Previous</button><button class="btn sm" id="guideNext" ${index===guide.tasks.length-1?'disabled':''}>Next →</button><button class="btn sm ghost" id="guideRecommend">Next needed step</button>${!ready?`<button class="btn sm ghost" id="guideDefer">${deferred?'Restore this step':'Defer this step'}</button>`:''}</div>
      <details class="guide-route"><summary>Browse the encounter path · ${guide.completed} supported, ${guide.deferred} deferred</summary><label>Jump to a step<select id="guideJump">${guide.groups.map(g=>`<optgroup label="${E(g.label)}">${guide.tasks.filter(t=>t.group===g.id).map(t=>`<option value="${E(t.id)}" ${t.id===active.id?'selected':''}>${t.status==='obtained'?'✓ ':t.status==='deferred'?'Deferred: ':t.status==='review'?'Review: ':''}${E(t.title)}</option>`).join('')}</optgroup>`).join('')}</select></label><p class="small">${E(guide.source_note)}</p><p class="small">${E(guide.limits)}</p></details>
      <details class="guide-coverage"><summary>What can my Subjective and Objective contain so far?</summary>${coverageHtml(guide.coverage)}<p class="small">${E(guide.checkpoint_note)}</p></details>
      <div id="recoveryBody" aria-live="polite"></div><div id="guideApplication" aria-live="polite"></div>`;
    const move=async(step,action='select')=>{const response=await request(`/api/session/${s.id}/guide`,{step,action});if(current?.id!==s.id)return;if(response.error){panel.querySelector('[data-guide-message]').textContent=response.error;return;}learning.case_guide=response;renderCaseGuide(s,learning);};
    panel.querySelector('#guidePrevious').onclick=()=>move(guide.tasks[index-1].id);
    panel.querySelector('#guideNext').onclick=()=>move(guide.tasks[index+1].id);
    panel.querySelector('#guideRecommend').onclick=()=>move(guide.recommended);
    panel.querySelector('#guideJump').onchange=e=>move(e.target.value);
    panel.querySelector('#guideDefer')?.addEventListener('click',()=>move(active.id,deferred?'restore':'defer'));
    panel.querySelector('#guideDraft')?.addEventListener('click',()=>draftQuestion(active.question,panel));
    panel.querySelector('#unstuckButton').onclick=()=>showHint(s);
    panel.querySelector('#guideChart')?.addEventListener('click',()=>document.getElementById('toolChart')?.click());
    panel.querySelector('#guideDecisionContinue')?.addEventListener('click',()=>move(active.id,'defer'));
    panel.querySelector('#guideOpenExam')?.addEventListener('click',()=>{
      if(typeof openExamPanel!=='function'){panel.querySelector('[data-guide-message]').textContent='Use the Examination control beside the patient to choose this action.';return;}
      if(window.pcmFocusExam?.(active.maneuver_id))return;
      openExamPanel();document.querySelector('#regionList [data-region=""]')?.click();
      const search=document.getElementById('manSearch');if(search){search.value=active.title;search.dispatchEvent(new Event('input',{bubbles:true}));search.focus();}
    });
    panel.querySelector('#guideFinish')?.addEventListener('click',()=>{const button=document.getElementById('btnEnd')||[...document.querySelectorAll('button')].find(b=>/finish encounter|end encounter/i.test(b.textContent)&&!panel.contains(b));if(button){button.scrollIntoView({block:'center',behavior:'auto'});button.focus();}else panel.querySelector('[data-guide-message]').textContent='Use Finish encounter in the encounter controls when you are ready to write.';});
    const history=data.hint_history?.[selected];if(history?.unlocked){const cue=history.cues[history.unlocked-1];drawHint(s,{...cue,unlocked:history.unlocked,wait_ms:history.wait_ms,replay:true});}
    showApplication(data,s);
  }
  function drawHint(s,result){
    const body=document.getElementById('recoveryBody');if(!body||current?.id!==s.id)return;
    const unlocked=result.unlocked||result.level;
    body.innerHTML=`<div class="recovery-card"><div class="recovery-routine">${result.routine.map((x,i)=>`<span><b>${i+1}</b>${E(x)}</span>`).join('')}</div><div class="cue-tabs" role="group" aria-label="Unlocked memory cues">${[1,2,3].map(n=>`<button class="btn sm" data-cue="${n}" aria-pressed="${n===result.level}" ${n>unlocked?'disabled':''}>Cue ${n}${n>unlocked?' · locked':''}</button>`).join('')}</div><h3>${E(result.text)}</h3><p class="small">${result.replay?'Revisiting an unlocked cue adds no assistance count.':'Pause and choose one action yourself before requesting more detail.'}</p><div class="guide-actions"><button class="btn sm" id="cueBack" ${result.level<=1?'disabled':''}>← Previous cue</button><button class="btn sm" id="cueNext" ${result.level>=unlocked?'disabled':''}>Next cue →</button>${unlocked<3?'<button class="btn" id="moreHint" disabled>Stronger cue shortly</button>':''}${result.question?'<button class="btn ghost" id="tryCue">Draft this cue question</button>':''}</div><details><summary>What you have actually obtained</summary>${result.obtained.map(e=>`<p class="evidence-quote"><span>#${e.seq}</span> ${E(e.text)}</p>`).join('')||'<p>No patient disclosures or completed examinations yet. Begin with the complaint.</p>'}</details></div>`;
    body.querySelectorAll('[data-cue]').forEach(b=>b.onclick=()=>showHint(s,Number(b.dataset.cue),result.step));
    body.querySelector('#cueBack').onclick=()=>showHint(s,result.level-1,result.step);
    body.querySelector('#cueNext').onclick=()=>showHint(s,result.level+1,result.step);
    const more=body.querySelector('#moreHint');if(more){const unlock=()=>{if(more.isConnected){more.disabled=false;more.textContent='Unlock cue '+(unlocked+1);}};if(result.wait_ms>0)setTimeout(unlock,result.wait_ms+50);else unlock();more.onclick=()=>showHint(s,unlocked+1,result.step);}
    body.querySelector('#tryCue')?.addEventListener('click',()=>{
      draftQuestion(result.question,document.getElementById('encounterGuide'));
      // The composer is behind this modal. Leaving the sheet open made a
      // successful draft look like a dead button.
      body.closest('dialog')?.close();
      document.getElementById('say')?.focus({preventScroll:true});
    });
  }
  async function showHint(s,level=null,step=null){
    const cueStep=step||selected;
    const prior=learning?.hint_history?.[cueStep];
    const requested=level??(prior?.unlocked||null);
    const payload={step:cueStep};if(requested)payload.level=requested;
    const result=await request(`/api/session/${s.id}/hint`,payload);const body=document.getElementById('recoveryBody');
    if(!body||current?.id!==s.id)return;
    if(result.error||result.wait){body.insertAdjacentHTML('beforeend',`<p role="status">${E(result.error||result.text)}</p>`);return;}
    learning.hint_history=learning.hint_history||{};
    const saved=learning.hint_history[cueStep]||{unlocked:0,cues:[]};saved.unlocked=result.unlocked;saved.wait_ms=result.wait_ms;saved.cues[result.level-1]=result;learning.hint_history[cueStep]=saved;
    drawHint(s,result);
  }
  async function repairPanel(s){
    if(document.getElementById('repairPractice'))return;
    const item=await request(`/api/session/${s.id}/repair`); const support=await request(`/api/session/${s.id}/learning`);if(item.error||current?.id!==s.id||document.getElementById('repairPractice'))return;
    const panel=document.createElement('section');panel.id='repairPractice';panel.className='repair-practice card';
    panel.innerHTML=`<span class="eyebrow">${item.requires_current_review?'Historical feedback':'A short repair before your next case'}</span><p class="small">${E(s.learning_mode)} · ${support.summary?.hints_used||0} hints · ${support.summary?.assisted?'assisted performance':'unassisted performance'}${s.branch?.is_branch?' · separate retry branch':''}</p><h2>${E(item.title)}</h2><p>${E(item.stem)}</p><div class="repair-choices">${item.choices.map((c,i)=>`<button class="btn" data-choice="${i}">${E(c)}</button>`).join('')}</div><div class="repair-result" role="status"></div><p class="small">Your original note and score remain locked. Repair attempts are tracked separately.</p>`;
    // A repair exercise is a follow-up to the feedback, not the thing you land
    // on and not something to read before it. It goes after the debrief tabs,
    // just above "your next practice".
    const host=document.querySelector('#view .wrap-wide,#view .wrap-mid')||document.getElementById('view');
    const next=host.querySelector('.debrief-next');
    const body=host.querySelector('#tabBody');
    if(next)next.before(panel);else if(body)body.after(panel);else host.append(panel);
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
    if(s.learning_mode==='guided'&&data.case_guide){learning=data;renderCaseGuide(s,data);return;}
    const previousStep=selected;learning=data;selected=data.selected;
    // Clearing the cue when the suggested stage moves on is right on the card.
    // It is not right while the student is reading that cue in an open sheet:
    // the assistance count is already spent and there is no way back to it.
    if(previousStep!==selected){const old=document.getElementById('recoveryBody');if(old&&!old.closest('dialog'))old.innerHTML='';}
    const panel=document.getElementById('encounterGuide');if(!panel)return;
    panel.querySelectorAll('[data-step]').forEach(b=>{b.classList.toggle('active',b.dataset.step===selected);b.setAttribute('aria-pressed',String(b.dataset.step===selected));});
    paintPurpose(data,s,selected);
    showApplication(data,s);
  }
  window.pcmLearningRender=s=>{lastEvidenceKey='';render(s);};
  window.pcmLearningState=s=>{syncGuide(s);};
})();
