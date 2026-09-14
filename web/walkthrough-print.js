import {buildPartnerSections, PRINT_EDITIONS} from './partner-print.js?v=136c87f6e7';
export {PRINT_EDITIONS};
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const assetURL=path=>new URL(path,import.meta.url).href;
let activeRoot=null,previewContext=null,preparation=0,stylePromise=null;
export function clearWalkthroughPrint(expectedRoot=null){if(expectedRoot&&expectedRoot!==activeRoot){expectedRoot.remove();return;}preparation++;if(previewContext){document.title=previewContext.title;previewContext=null;}document.body.removeAttribute('data-walkthrough-print');document.body.removeAttribute('data-walkthrough-preview');document.getElementById('walkthroughPrintToolbar')?.remove();activeRoot?.remove();activeRoot=null;window.pcmPrintReport=null;}
export function showWalkthroughPreview({onPrint,onClose}){
 if(!activeRoot||!window.pcmPrintReport)throw Error('Prepare the print edition first.');
 if(!previewContext)previewContext={title:document.title};document.title=activeRoot.dataset.documentTitle;
 let bar=document.getElementById('walkthroughPrintToolbar');
 if(!bar){bar=document.createElement('nav');bar.id='walkthroughPrintToolbar';bar.setAttribute('aria-label','Print preview controls');document.body.insertBefore(bar,activeRoot);}
 bar.innerHTML=`<div><b>${esc(PRINT_EDITIONS[window.pcmPrintReport.edition].label)}</b><span>${window.pcmPrintReport.pages} Letter sheets · ${PRINT_EDITIONS[window.pcmPrintReport.edition].paper==='portrait'?'portrait':window.pcmPrintReport.edition==='study'?'separate sections; answer key last':'read left column, then right'}</span></div><button type="button" id="pwNativePrint">Print / Save PDF</button><button type="button" id="pwClosePrint">Return to case</button>`;
 bar.querySelector('#pwNativePrint').onclick=onPrint;bar.querySelector('#pwClosePrint').onclick=onClose;
 activeRoot.setAttribute('aria-hidden','false');activeRoot.setAttribute('aria-label',PRINT_EDITIONS[window.pcmPrintReport.edition].label+' preview');
 document.body.setAttribute('data-walkthrough-preview','true');document.body.setAttribute('data-walkthrough-print','approved');
 window.scrollTo(0,0);bar.querySelector('#pwNativePrint').focus();
}

async function loadStyle(){
 if(stylePromise)return stylePromise;
 if(document.getElementById('walkthroughPrintCSS')?.sheet)return;
 stylePromise=new Promise((resolve,reject)=>{const link=document.createElement('link');link.id='walkthroughPrintCSS';link.rel='stylesheet';link.href=assetURL('walkthrough-print.css?v=0893d1f366');link.onload=resolve;link.onerror=()=>{link.remove();reject(Error('The print layout could not load. Please reconnect and try again.'));};document.head.append(link);});
 try{await stylePromise;}catch(error){stylePromise=null;throw error;}
}
function makePage(root,l,title,kind,paper='landscape'){
 const page=document.createElement('section');page.className='pw-page '+(kind==='storyboard'?'pw-storyboard-page':'pw-reading-page');page.dataset.section=title;page.dataset.paper=paper;page.dataset.kind=kind;
 page.innerHTML=`<header class="pw-page-header"><span class="pw-brand">Chat CSE <i>/</i> ${esc(title)}</span><span>${esc(l.patient.name)} · ${esc(l.variant_label)}</span></header><div class="pw-columns"><div class="pw-column"></div>${paper==='portrait'?'':'<div class="pw-column"></div>'}</div><footer class="pw-page-footer"><span>${esc(l.case_id)} · ${esc(l.variant_id)} · Print edition 2026-09-14</span><span class="pw-page-count"></span></footer>`;root.append(page);return page;
}
async function decodeImages(root){
 const images=[...root.querySelectorAll('img')];
 const failures=[];
 await Promise.all(images.map(async img=>{try{await img.decode();if(!img.naturalWidth)throw Error();}catch{failures.push(img.getAttribute('src'));}}));
 if(failures.length)throw Error('A walkthrough image could not load. Reconnect and try Print case documents again.');
}
function paginate(root,l,sections,edition){
 const report={edition,case_id:l.case_id,variant_id:l.variant_id,pages:0,turns:(l.timeline||[]).length,oversized:[],images:0,sections:[],evidence_strategy:'Actor facts are separate from obtained evidence. Revised note references identify demonstrated topics and exact examinations; they are not automatic semantic verification.'};
 let page=null,column=null,colIndex=0,previousKind=null,previousPaper=null;
 for(const section of sections){
  const paper=section.paper||'landscape';
  const continueReading=section.kind===previousKind&&previousPaper===paper&&!section.startPage;
  if(!continueReading){page=makePage(root,l,section.title,section.kind,paper);column=page.querySelector('.pw-column');colIndex=0;}

  previousKind=section.kind;previousPaper=paper;
  const next=()=>{if(paper!=='portrait'&&colIndex===0){colIndex=1;column=page.querySelectorAll('.pw-column')[1];}else{page=makePage(root,l,section.title,section.kind,paper);colIndex=0;column=page.querySelector('.pw-column');}};
  const queue=section.blocks.map(html=>{const holder=document.createElement('template');holder.innerHTML=html;return holder.content.firstElementChild;});
  for(let n=0;n<queue.length;n++){
   const block=queue[n];column.append(block);
   // Headings stay with enough of the following block to preserve reading order.
   let overflow=column.scrollHeight>column.clientHeight+1;
   if(!overflow&&block.classList.contains('pw-heading')&&queue[n+1]){
    // Keep the section label, navigation line, and first actual answer together.
    const preview=[];
    for(let look=n+1;look<queue.length;look++){const child=queue[look].cloneNode(true);column.append(child);preview.push(child);if(!child.classList.contains('pw-heading')&&!child.classList.contains('rp-crossref'))break;}
    overflow=column.scrollHeight>column.clientHeight+1;preview.forEach(child=>child.remove());
   }
   if(overflow&&column.children.length>1){block.remove();next();column.append(block);}
   if(column.scrollHeight>column.clientHeight+1){
    // Split by direct children, preserving complete paragraphs and every original word.
    const children=[...block.children];
    if(children.length>1){
     block.remove();let part=block.cloneNode(false);part.dataset.continuation='false';
     column.append(part);
     for(const child of children){
      part.append(child);
      if(column.scrollHeight>column.clientHeight+1&&part.children.length>1){child.remove();next();part=block.cloneNode(false);part.dataset.continuation='true';part.removeAttribute('data-anchor');part.removeAttribute('id');part.removeAttribute('data-turn-index');part.removeAttribute('data-note-link');column.append(part);part.append(child);}
      if(column.scrollHeight>column.clientHeight+1)report.oversized.push({section:section.title,text:child.textContent.slice(0,100)});
     }
    }else report.oversized.push({section:section.title,text:block.textContent.slice(0,100)});
   }
  }
  report.sections.push({name:section.title,blocks:section.blocks.length});
 }
 const pages=[...root.querySelectorAll('.pw-page')];report.pages=pages.length;report.images=root.querySelectorAll('img').length;
 pages.forEach((page,i)=>{page.querySelector('.pw-page-count').textContent=`${i+1} / ${pages.length}`;});
 const anchors=new Map();
 pages.forEach((page,i)=>page.querySelectorAll('[data-anchor]').forEach(el=>{if(!anchors.has(el.dataset.anchor)){el.id='rp-'+el.dataset.anchor;anchors.set(el.dataset.anchor,{page:i+1,element:el});}}));
 report.missingReferences=[];
 root.querySelectorAll('[data-page-ref]').forEach(link=>{const target=anchors.get(link.dataset.pageRef);if(target){link.querySelector('.rp-page-ref').textContent='p. '+target.page;link.onclick=event=>{event.preventDefault();target.element.scrollIntoView({block:'center'});};}else {report.missingReferences.push(link.dataset.pageRef);}});
 return report;
}
export async function prepareWalkthrough(l,{edition='patient'}={}){
 clearWalkthroughPrint();const generation=preparation;const check=()=>{if(generation!==preparation)throw Error('Print preparation was canceled. Choose your materials again.');};await loadStyle();check();await document.fonts.ready;check();
 const root=document.createElement('div');root.id='walkthroughPrint';root.dataset.documentTitle=`${l.patient.name} - ${PRINT_EDITIONS[edition]?.label||'Print'} - ${l.variant_label}`;root.dataset.edition=edition;root.dataset.paper=PRINT_EDITIONS[edition]?.paper;root.setAttribute('aria-hidden','true');document.body.append(root);activeRoot=root;
 const sections=buildPartnerSections(l,edition);
 // Preload each unique local image before measuring physical page geometry.
 const preloader=document.createElement('div');preloader.innerHTML=sections.flatMap(s=>s.blocks).join('');root.append(preloader);
 try{
  await decodeImages(preloader);check();preloader.remove();
  const report=paginate(root,l,sections,edition);
  await decodeImages(root);check();
  if(report.missingReferences.length)throw Error('A script cross-reference could not be resolved. No pages were removed.');
  if(report.oversized.length)throw Error('A section is too long for the print layout. The lesson has not been truncated. Please use the written lesson while this layout is corrected.');
  window.pcmPrintReport=report;return {root,report};
 }catch(error){clearWalkthroughPrint(root);throw error;}
}
