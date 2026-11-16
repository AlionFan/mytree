'use strict';
(async () => {
const app = document.getElementById('app');
const $ = (id) => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const {math:mathHTML,rich:richHTML,field:mathField}=MathUI;
const state = {questionSearch:{},pageBatch:null,pageStudies:{},activeReadingId:null,previewReading:null,batchBusy:false,batchInFlight:0,batchCancelled:false,pageRequestId:null,sourceGeneration:null,stage:'select',showOriginal:false,problem:'', steps:'', result:null, exercises:[], photo:null, photoData:null, photoEpoch:0, ocrPending:false, ocrResult:null, ocrBusy:false, hintLevel:1, tutorMessages:[], capabilities:null, fileName:"", fileKind:"", documentData:null, page:1, pageCount:0, sourceImage:null, sourceLoading:false, sourceError:"", cropMode:false, cropBox:null, dragBox:null};
const account = await window.MytreeAccount;
let student;
if(account) student=account.profile_id;
else try { student = localStorage.getItem('mytree_demo'); if (!/^[A-Za-z0-9_-]{1,64}$/.test(student || '')) { student = 'local_' + crypto.randomUUID().replaceAll('-',''); localStorage.setItem('mytree_demo', student); } }
catch { student = 'session_' + Math.random().toString(36).slice(2); }
let renderVersion = 0;
let explorerController=null;
const names = {'F-NOT-FINISHED':'分解得不彻底','F-NOT-PRODUCT':'还没有写成乘积','F-COMMON-PARTIAL':'公因式没提干净','F-SIGN':'括号前后的符号','F-MIX-FORMULA':'两种公式混淆','F-COEFF-LOST':'漏写提出的公因数','R-CANCEL-TERM':'把加减项当因式约分','R-CANCEL-INCOMPLETE':'约分还不彻底','R-SIGN':'分式的符号','R-DOMAIN':'分母的取值限制','CALC':'两行变形不等价'};
const requestId = () => crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
const formatTime = (v, withTime = true) => new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',...(withTime?{hour:'2-digit',minute:'2-digit'}:{})}).format(new Date(v));
const post = (url, data, timeoutMs=20000) => api(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({student,...data}),timeoutMs});
async function api(path, options={}) {
 const {timeoutMs=20000,...requestOptions}=options;
 const controller = new AbortController(); const timeout = setTimeout(()=>controller.abort(),timeoutMs);
 try {
  const response = await fetch(path, {...requestOptions, signal:controller.signal});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error==='object'?data.error.message:(data.error || `暂时没有连接成功（${response.status}）`));
  return data;
 } catch(error) {
  if(error.name === 'AbortError') throw new Error('等待有点久，请再试一次。');
  if(error instanceof TypeError) throw new Error('暂时连不上学习桌，请检查网络后重试。');
  throw error;
 } finally { clearTimeout(timeout); }
}
const getProfile = () => api(`/api/profile?student=${encodeURIComponent(student)}`);
const agentCall=async(operation,input,identity=requestId())=>{const value=await api('/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({schema_version:'1.0',request_id:identity,operation,client:{type:'web',name:'mytree',version:'2.1'},subject:{profile_id:student},input})});return value.output;};
const notice = (message, type='') => `<div class="notice ${type}" role="${type==='error'?'alert':'status'}">${esc(message)}</div>`;
const learning=LearningUI.setup({agent:agentCall,api,post,esc,richHTML,mathField,notice,app,student,practice:(card,reviewId)=>practiceFromCard(card,reviewId),navigate:path=>{history.pushState({},'',path);render();window.scrollTo(0,0);}});
const diagramController=DiagramUI.setup({post,esc,richHTML,notice,onAccess:(id,level)=>{if(id===state.result?.diagnosis_id)state.hintLevel=Math.max(state.hintLevel,level);}});
function intro() {const title=({'/':'学习桌','/tree':'知识树','/plan':'复习计划','/parent':'家长','/explore':'探索'})[location.pathname]||'学习';return `<div class="page-intro"><h1>${title}</h1></div>`;}
function treePicture(lit) {
 return `<svg class="mini-tree" viewBox="0 0 260 160" aria-label="已点亮 ${lit} 个知识点的小树" role="img"><path d="M130 150V39M130 111L90 82M130 91L166 63M130 64L113 43" fill="none" stroke="#9eac8d" stroke-width="5" stroke-linecap="round"/><path d="M130 150h-35m35 0h35" stroke="#cad2bc" stroke-width="2"/>${[[74,65,-28],[166,49,34],[103,29,-27],[130,16,0],[160,93,45],[101,106,-45],[191,58,55],[79,115,-55]].map(([x,y,angle],i)=>`<ellipse cx="${x}" cy="${y}" rx="13" ry="23" transform="rotate(${angle} ${x} ${y})" fill="${i<lit?'#5a8865':'#dde4cf'}"/>`).join('')}</svg>`;
}
function exerciseHTML(items,prefix='answer') {
 return items.map((it,i)=>`<div class="exercise" data-exercise="${esc(it.id)}"><span class="source-tag">巩固练习 ${i+1}</span>${it.verification?`<p class="field-tip">${esc(it.verification.label)}</p>`:''}<div class="math-prose">${richHTML(it.question_md||it.question,!it.question_md)}</div>${it.match_reason?`<p class="field-tip match-reason">${esc(it.match_reason)}</p>`:''}${it.domain?.length?`<div class="field-tip">保持原题范围：${richHTML(it.domain.join('；'),true)}</div>`:''}<label for="${prefix}-${esc(it.id)}">第 ${i+1} 题答案</label><div class="row answer-row">${(it.grading==='choice'||it.answer_kind==='choice')?`<select id="${prefix}-${esc(it.id)}" data-answer aria-label="第 ${i+1} 题答案"><option value="">选择选项</option>${['A','B','C','D'].map(label=>`<option value="${label}">${label}</option>`).join('')}</select>`:mathField('',`id="${prefix}-${esc(it.id)}" data-answer aria-label="第 ${i+1} 题答案"`)}<button class="ghost" data-check>检查</button></div><p class="field-tip">${(it.grading==='choice'||it.answer_kind==='choice')?'选择一个选项后检查。':'点击公式框，用数学键盘输入分数、根号或集合。'}</p><p class="feedback" data-feedback role="status"></p></div>`).join('');
}
async function renderStudent(version) {
 app.innerHTML = intro('让好奇心带路','今天，想明白一点新东西。','从一道题开始，把方法变成自己的。') + `
 <section id="today-tasks" class="panel today-panel" aria-live="polite">正在读取今日待办…</section><div class="desk-grid"><section class="panel capture-panel"><h2 id="capture-title" class="sr-only">拍题</h2>
 <div class="upload-zone" id="upload-zone"><span class="upload-symbol" aria-hidden="true"><svg viewBox="0 0 124 92" fill="none"><rect x="27" y="9" width="66" height="76" rx="9" transform="rotate(-8 27 9)" fill="#e6eee5"/><rect x="35" y="8" width="66" height="76" rx="9" fill="#fff" stroke="#9bad9d" stroke-width="1.5"/><path d="M47 25h30M47 33h19M48 65l10-12 10 6 14-19" stroke="#27624d" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="92" cy="68" r="17" fill="#f5dca6"/><path d="M86 68h12m-6-6v12" stroke="#78561f" stroke-width="2" stroke-linecap="round"/></svg></span><div class="upload-actions"><button id="open-camera"><svg class="button-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 1-2h6l1 2h4v15H4V5h4Z"/><circle cx="12" cy="12" r="4"/></svg>拍照录题</button><button id="open-file" class="ghost">上传图片 / PDF</button></div><input id="camera-input" type="file" accept="image/*" capture="environment" hidden><input id="file-input" type="file" accept="image/jpeg,image/png,image/webp,image/gif,image/bmp,application/pdf,.pdf" hidden><p class="field-tip">图片不超过 10 MB，PDF 不超过 20 MB</p></div>
 <div class="capture-progress" aria-label="拍题步骤"><span data-stage="select">1 选页</span><span data-stage="review">2 识别</span><span data-stage="learn">3 学习</span></div><div class="row capture-secondary"><button id="back-to-source" class="ghost small hidden">返回选题</button><button id="view-original" class="ghost small hidden">查看原题</button></div><div id="source-area"></div><details class="capture-help"><summary>上传说明</summary><p id="photo-boundary" class="field-tip"></p></details><button id="recognize-photo" class="full hidden" disabled>识别选中的题目</button><div id="recognition-message" aria-live="polite"></div><div id="recognition-review" class="hidden"></div><div id="diagnose-message" aria-live="polite"></div>
 <div id="result" class="result">${state.result?renderDiagnosis(state.result):''}</div></section>
</div><section class="panel saved-cards-panel" id="saved-cards" aria-live="polite">正在读取题目卡…</section>`;
 if(state.exercises.length && $('practice-list')) $('practice-list').innerHTML = exerciseHTML(state.exercises);
 renderSource();
 if(state.pageBatch)renderPageItems();else if(state.ocrResult)showRecognitionConfirmation(state.ocrResult);
 syncStage();
 await Promise.allSettled([refreshSidebar(version), refreshCapabilities(version)]);
}
async function refreshSidebar(version=renderVersion){return learning.refreshHome(()=>version===renderVersion);}
async function refreshCapabilities(version=renderVersion) {
 try {const caps=await api('/api/capabilities');state.capabilities=caps;if(version!==renderVersion)return;
 const status=$('ai-status');if(status)status.textContent=caps.vision&&caps.conversation?'拍照与文件识别 · AI 辅助理解':'AI 识别暂不可用，请稍后重试';
 updateRecognitionButton();
 if($('photo-boundary'))$('photo-boundary').textContent=caps.vision?'点击识别后，仅把当前页面或框选区域发给 AI。清晰题会自动整理；看不清的题先跳过，可稍后重拍。':'AI 识别暂未配置，可以先上传、预览文件，稍后再试。';
 } catch(e) {if(version===renderVersion&&$('photo-boundary'))$('photo-boundary').textContent='暂时连不上识别服务，文件预览仍保留，可以稍后重试。';}
}
function renderTutorMessages() {
 return state.tutorMessages.map(turn=>`<div class="tutor-turn ${turn.role==='user'?'learner':'teacher'}"><span class="source-tag">${turn.role==='user'?'我的问题':turn.fallback?'本题分级提示':'AI 辅助讲解'}</span><div class="math-prose">${richHTML(turn.content,state.result?.analysis?.engine!=='junior')}</div>${(turn.equations||[]).map(eq=>`<div class="formula">${mathHTML(eq.left,false,!eq.latex)} ${mathHTML('=')} ${mathHTML(eq.right,false,!eq.latex)}</div>`).join('')}${turn.fallback?'<p class="field-tip">本次生成未通过检查，已回到这道题的分级提示。</p>':''}</div>`).join('');
}
function renderDiagnosis(result) {
 if(!result.ok)return notice(result.message+' 请对照原图核对后再试一次。','error');
 const a=result.analysis,learning=a.status==='not_attempted',old=a.engine!=='junior',pending=a.status==='ai_review';
 const original=result.wrong_card?.student_steps||state.ocrResult?.steps||[];const shownSteps=original.length?original.map((text,i)=>({i:i+1,text,ok:a.study_mode==='lesson_only'?null:(a.steps||[])[i]?.ok??null})):(a.steps||[]);const presence=state.ocrResult?.answer_presence;const emptyWork=presence==='absent'?'原图中未发现作答。':presence==='present'?'检测到作答，但文字尚未读完整，请对照原图。':'作答区域尚未读清，暂不能确定具体内容。';
 let message=a.study_mode==='lesson_only'?'':learning?'这道题尚未作答，先理解题意，再尝试解题。':pending?'':a.status==='correct'?'支持核验的作答与题目相符，检查结果已保存。':a.status==='incomplete'?'前面的变形等价，最后还可以再走一步。':`第 ${a.first_error} 行需要再看一看，程序核对没有通过。`;
 return `${state.ocrResult?.inferred?notice('按你确认的读法核对，识别推断不代表数学结论已经通过。'):''}<h2 class="result-title">解析</h2><div class="current-question math-prose">${richHTML(a.problem||state.problem,old)}</div><span class="source-tag">${esc(pending?'AI讲解':a.verification?.label||'学习记录')}</span>${message?notice(message,a.status==='correct'?'success':''):''}
 <details class="study-details"><summary>我的作答</summary>${!shownSteps.length?`<p class="field-tip">${esc(emptyWork)}</p>`:''}<div class="steps">${shownSteps.map(row=>`<div class="step ${row.ok===false?'bad':row.ok===null?'unknown':''}"><span class="n">${String(row.i).padStart(2,'0')}</span><div class="math-prose">${row.latex?mathHTML(row.latex):richHTML(row.text,old)}</div><span class="status" aria-label="${row.ok===false?'核验不通过':row.ok===null?'待核对':row.ok==='incomplete'?'尚未完成':'核验通过'}">${row.ok===false?'×':row.ok===null?'—':row.ok==='incomplete'?'…':'✓'}</span></div>`).join('')}</div></details>
 ${a.assessment&&!/尚不能独立核验|暂不据此|进一步核对/.test(a.assessment)?`<div class="assessment math-prose"><span class="source-tag">AI讲解</span>${richHTML(a.assessment)}</div>`:''}
 ${a.domain?.length?`<div class="field-tip">保留原题取值范围：${richHTML(a.domain.join('；'),true)}</div>`:''}
 ${a.hints?.length?`<div id="hints">${Array.from({length:a.hint_levels_available||a.hints.length},(_,i)=>a.hints[i]||'').map((hint,i)=>`<section class="hint-block ${i?'hidden':''}"><button class="${i?'':'primary-next'}" data-hint="${i}" aria-expanded="false" aria-controls="hint-${i}" ${i?'disabled':''}><span><span class="hint-number">${String(i+1).padStart(2,'0')}</span>${['先找方向','再想关键一步','查看完整思路'][i]}</span><span aria-hidden="true">＋</span></button><div id="hint-${i}" class="hidden math-prose">${richHTML(hint,old)}</div></section>`).join('')}</div>`:''}
 ${a.visual_svg?`<div style="margin:16px 0"><button class="ghost full" data-show-visual aria-expanded="false" aria-controls="visual">用图形理解这道题 <span class="small-text">（含解法）</span></button><div id="visual" class="visual-box hidden">${a.visual_svg}${a.visual_svg.includes('data-rearranged')?'<button class="ghost small" data-rearrange>把两块拼起来 →</button>':''}</div></div>`:''}
 ${a.card?`<details class="knowledge-details"><summary>知识点</summary><div class="knowledge"><h3>${esc(a.card.title)}</h3><div class="math-prose">${richHTML(a.card.body,old)}</div><div class="muted math-prose">${richHTML(a.card.tip,old)}</div></div></details>`:''}
 <details class="study-details"><summary>我还有疑问，展开问一问</summary><section class="tutor-section"><h3>围绕这道题，一起想</h3><p class="field-tip">一次想明白一个问题。讲解跟随已展开的提示级别。</p><div class="row tutor-suggestions"><button class="ghost small" data-tutor-prompt="这道题应该从哪里开始想？">从哪里开始想？</button><button class="ghost small" data-tutor-prompt="请用一个具体例子或图形关系，换一种说法帮我理解。">换个例子讲讲</button></div><div id="tutor-messages" aria-live="polite">${renderTutorMessages()}</div><form id="tutor-form"><label for="tutor-question">我想问</label><div class="row"><input id="tutor-question" maxlength="300" placeholder="说说哪里还没想明白" autocomplete="off"><button type="submit">提问</button></div></form><div id="tutor-status" aria-live="polite"></div>
 <div class="learning-feedback"><p class="field-tip">这次讲解对你有帮助吗？</p><div class="row"><button class="ghost small" data-rating="understood">听懂了</button><button class="ghost small" data-rating="confusing">再讲简单些</button><button class="ghost small" data-rating="incorrect">可能有误</button></div><div id="feedback-status" aria-live="polite"></div></div></section></details>
 ${cardNoteHTML(result.wrong_card)}<details class="study-details"><summary>再做对应练习</summary><div class="side-section"><div class="panel-heading"><span class="number">02</span><h2>巩固这个知识点</h2></div><p class="small-text muted">练习会对应这道题的方法；AI会按原题考点延伸三道类似题，反馈供参考。</p><button id="start-practice" class="full">开始巩固练习 →</button><div id="practice-list" class="practice-list" aria-live="polite"></div></div></details>`;
}
async function diagnoseInput() {
 if(!state.ocrResult)return;
 const button = $('confirm-ocr'); const out = $('diagnose-message');
 const pure=$('problem-math');
 state.problem=pure?'\\('+pure.value.trim()+'\\)':$('problem-source').value.trim();
 state.steps=[...document.querySelectorAll('[data-step-source]')].map(el=>el.tagName==='MATH-FIELD'?'\\('+el.value.trim()+'\\)':el.value.trim()).filter(Boolean).join('\n');
 if(!state.problem){out.innerHTML=notice('题干没有读完整，请核对识别结果或重新上传。','error');return;}
 const steps = state.steps.split('\n').map(s=>s.trim()).filter(Boolean);
 if(steps.length>30 || steps.some(s=>s.length>1500)){ out.innerHTML=notice('最多保留 30 行作答，每行不超过 1500 字。','error');return; }
 button.disabled = true; button.textContent=steps.length?'正在检查作答…':'正在准备讲解…';out.innerHTML=notice(steps.length?'正在比较每一步变形…':'这份文件没有作答，正在准备这道题的学习内容…');
 const target = $('result');
 try {
  const result = await post('/api/study',{problem:state.problem,problem_latex:pure?.value||'',steps,recognition:state.ocrResult,confirmed_reading_id:state.ocrResult.reading_id,request_id:requestId()},95000);
  state.result=result; state.stage='learn';state.showOriginal=false;state.exercises=[]; state.hintLevel=1; state.tutorMessages=[]; refreshSidebar();
  if(target.isConnected){ target.innerHTML=renderDiagnosis(result);out.innerHTML='';if(result.ok&&state.ocrResult&&$('recognition-message'))$('recognition-message').innerHTML=notice('识别内容已确认，检查结果已显示在下方。','success'); syncStage();target.scrollIntoView({block:'start',behavior:'auto'}); }
 } catch(e) {if(out.isConnected)out.innerHTML=notice(e.message,'error');}
 finally {if(button.isConnected){button.disabled=false;button.textContent=state.steps?'重新核对并检查作答':'重新核对并开始学习';}}
}
function practiceFromCard(card,reviewId){
 let box=$('card-practice-dialog');if(!box){box=document.createElement('dialog');box.id='card-practice-dialog';box.className='knowledge-lesson-dialog';document.body.append(box);}
 box.innerHTML=`<div class="section-title"><h2>巩固练习</h2><button class="ghost small" data-close-card-practice>关闭</button></div><div class="math-prose">${richHTML(card.problem,true)}</div><button data-start-card-practice>生成同类练习</button><div class="practice-list" data-answer-prefix="card-answer" aria-live="polite"></div>`;
 box.querySelector('[data-close-card-practice]').onclick=()=>box.close();const button=box.querySelector('[data-start-card-practice]');button.onclick=()=>startPractice(button,reviewId?{review_id:reviewId}:{diagnosis_id:card.diagnosis_id},box.querySelector('.practice-list'));
 box.showModal();button.click();
}
async function startPractice(button, data, box=$('practice-list')) {
 if(!box)return; button.disabled=true;
 box.innerHTML='<p class="muted small-text" role="status">正在根据原题考点生成三道延伸练习…</p>';
 try{ const result=await post('/api/practice', data,95000);if(box.isConnected){state.exercises=result.items;box.innerHTML=exerciseHTML(result.items,box.dataset.answerPrefix||'answer');}}
 catch(e){if(box.isConnected)box.innerHTML=notice(e.message,'error');}
 finally{button.disabled=false;}
}
async function checkExercise(button) {
 const item = button.closest('[data-exercise]');const input=item.querySelector('[data-answer]');const feedback=item.querySelector('[data-feedback]');
 const answer=input.value.trim();if(!answer){feedback.className='feedback bad';feedback.textContent='先写出你的答案。';input.focus();return;}
 button.disabled=true; feedback.textContent='正在检查…';
 try{const result=await post('/api/practice/check',{exercise_id:item.dataset.exercise,answer},95000);feedback.className='feedback '+(result.correct?'good':'bad');feedback.textContent=result.message;if(result.correct===null){feedback.className='feedback';feedback.innerHTML=richHTML(result.message)+'<details><summary>查看参考答案与解法</summary><div class="math-prose">'+richHTML(result.reference_answer||'',true)+richHTML(result.reference_solution||'',true)+'</div></details>';}
 if(result.correct){refreshSidebar();button.textContent='已做对 ✓';input.readOnly=true;if(input.tagName==='SELECT')input.disabled=true;state.exercises=state.exercises.filter(e=>e.id!==item.dataset.exercise);}
 else button.disabled=false;
 }catch(e){feedback.className='feedback bad';feedback.textContent=e.message;button.disabled=false;}
}
function cancelPageWork(){
 state.batchCancelled=true;
 if(state.pageBatch){const batch=state.pageBatch;post('/api/recognize/page/cancel',{batch_id:batch.batch_id,source_revision:batch.source_revision}).catch(()=>{});}
}
function resetRecognition(fresh=true) {
 cancelPageWork();state.questionSearch={};state.pageBatch=null;state.pageStudies={};state.activeReadingId=null;state.previewReading=null;state.batchBusy=false;state.batchInFlight=0;state.batchCancelled=false;
 if(fresh||!state.pageRequestId){state.pageRequestId=requestId();state.sourceGeneration=requestId();}
 state.stage='select';state.showOriginal=false;state.problem='';state.steps='';state.ocrResult=null;state.ocrPending=false;state.result=null;state.exercises=[];state.tutorMessages=[];state.hintLevel=1;
 for(const id of ['recognition-message','recognition-review','result','diagnose-message'])if($(id)){$(id).innerHTML='';if(id==='recognition-review')$(id).classList.add('hidden');}
}
function syncStage(){
 const stage=state.stage;
 app.classList.toggle('source-view',!!state.fileName&&(stage==='select'||state.showOriginal));
 const hide=(id,hidden)=>$(id)?.classList.toggle('hidden',hidden);
 hide('upload-zone',!!state.fileName||stage!=='select');
 hide('source-area',stage!=='select'&&!state.showOriginal);
 hide('recognition-review',stage!=='review'&&!state.pageBatch);hide('result',(!state.result&&!state.previewReading)||!['learn','batch'].includes(stage));
 hide('back-to-source',stage==='select');hide('view-original',stage==='select');
 hide('photo-boundary',stage!=='select'||state.cropMode);
 document.querySelectorAll('.crop-controls,.page-controls,#replace-file,#crop-help').forEach(el=>el.classList.toggle('hidden',stage!=='select'));
 document.querySelector('.page-intro')?.classList.toggle('hidden',!!state.fileName);
 if($('view-original')){$('view-original').textContent='▧';$('view-original').setAttribute('aria-label',state.showOriginal?'收起原题':'查看原题');$('view-original').title=state.showOriginal?'收起原题':'查看原题';}if($('back-to-source')){$('back-to-source').textContent='↩';$('back-to-source').setAttribute('aria-label','返回选题');$('back-to-source').title='返回选题';}
 if($('capture-title'))$('capture-title').textContent=state.pageBatch?'这一页，逐题开始学习':stage==='review'?'核对题目与作答':stage==='learn'?'从这一步，继续想明白':'选一道题，开始学习';
 document.querySelectorAll('[data-stage]').forEach(el=>el.setAttribute('aria-current',el.dataset.stage===(state.ocrBusy&&!state.result?'review':stage==='batch'?'review':stage)?'step':'false'));
 document.querySelector('.desk-grid')?.classList.toggle('capture-active',!!state.fileName);
 hide('today-tasks',!!state.fileName);hide('saved-cards',!!state.fileName);
 updateRecognitionButton();
}
function updateRecognitionButton(){const button=$('recognize-photo');if(button){button.classList.toggle('hidden',!state.fileName||state.stage!=='select'||state.cropMode);button.disabled=!state.photoData||!state.capabilities?.vision||state.ocrBusy||state.sourceLoading||state.cropMode;button.textContent=state.ocrBusy?'正在识别与整理…':state.pageBatch?'返回已识别内容':'识别并整理';}}
function renderSource(){
 const box=$('source-area');if(!box)return;
 if(!state.fileName){box.innerHTML='';syncStage();return;}
 box.innerHTML=`<div class="source-heading"><button id="close-source" class="ghost small" aria-label="返回拍摄上传入口">×</button><button id="retake-photo" class="ghost small" aria-label="重新拍摄" title="重新拍摄"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 1-2h6l1 2h4v15H4V5h4Z"/><circle cx="12" cy="12" r="4"/></svg></button><button id="replace-file" class="ghost small" title="当前文件：${esc(state.fileName)}" aria-label="重新上传，当前文件：${esc(state.fileName)}"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m4 17 5-6 4 4 3-3 5 6"/><circle cx="16" cy="8" r="1"/></svg></button></div>${state.fileKind==='pdf'?`<div class="page-controls"><button class="ghost small" id="prev-page" aria-label="上一页" ${state.page<=1||state.sourceLoading?'disabled':''}>‹</button><label for="pdf-page" class="sr-only">选择 PDF 页码</label><select id="pdf-page" aria-label="选择 PDF 页码" ${state.sourceLoading?'disabled':''}>${Array.from({length:state.pageCount||1},(_,i)=>`<option value="${i+1}" ${state.page===i+1?'selected':''}>${i+1} / ${state.pageCount||'…'}</option>`).join('')}</select><button class="ghost small" id="next-page" aria-label="下一页" ${state.page>=state.pageCount||state.sourceLoading?'disabled':''}>›</button></div>`:''}${state.sourceLoading?'<p class="source-wait" role="status">正在准备预览…</p>':''}${state.sourceError?notice(state.sourceError,'error'):''}<div class="document-preview"><canvas id="source-canvas" tabindex="0" role="img" aria-label="试题原图，可直接拖动框选" aria-describedby="crop-help"></canvas></div><p id="crop-help" class="sr-only">拖动选择题目，松开后应用。两指滑动、滚轮、PageUp或PageDown浏览长图，Alt方向键平移；双击或按Escape恢复整页。方向键调整选区，Shift方向键改变大小，Enter应用。</p><span id="crop-status" class="sr-only" aria-live="polite">${state.cropBox?'已选择一个区域':'整页识别'}</span>`;

 if(state.sourceImage){paintPreview();const preview=$('source-canvas').parentElement;preview.scrollLeft=72;preview.scrollTop=72;}
 syncStage();
}
function paintPreview(){const canvas=$('source-canvas');const image=state.sourceImage;if(!canvas||!image)return;canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const rect=state.cropMode?state.dragBox:state.cropBox;if(rect){ctx.fillStyle='rgba(24,49,39,.35)';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,rect.x,rect.y,rect.w,rect.h,rect.x,rect.y,rect.w,rect.h);ctx.strokeStyle='#2e6655';ctx.lineWidth=Math.max(3,canvas.width/150);ctx.strokeRect(rect.x,rect.y,rect.w,rect.h);}}
function readFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('文件没有读完整，请重新选择。'));reader.readAsDataURL(file);});}
async function loadPreview(data,epoch){const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(new Error('图片无法打开，请换一张 JPG、PNG 或 WebP 图片。'));image.src=data;});if(epoch!==state.photoEpoch)return;state.sourceImage=image;state.photo=data;state.cropBox=null;state.dragBox=null;state.cropMode=false;const scale=Math.min(1,2400/Math.max(image.naturalWidth,image.naturalHeight));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);state.photoData=canvas.toDataURL('image/jpeg',.88);}
async function choosePhoto(file){
 if(!file)return;cropPointers.clear();cropGesture=null;multiPan=null;multiGesture=false;const epoch=++state.photoEpoch;resetRecognition();state.photoData=null;state.sourceImage=null;state.photo=null;state.documentData=null;state.page=1;state.pageCount=0;state.sourceError='';state.sourceLoading=true;state.ocrBusy=false;state.cropMode=false;state.cropBox=null;state.fileName=file.name;state.fileKind=file.type==='application/pdf'||/\.pdf$/i.test(file.name)?'pdf':'image';state.archivePromise=null;renderSource();
 try{const max=(state.fileKind==='pdf'?20:10)*1024*1024;if(file.size>max)throw new Error(state.fileKind==='pdf'?'PDF 请小于 20 MB。':'图片请小于 10 MB。');if(state.fileKind==='image'&&file.type&&!file.type.startsWith('image/'))throw new Error('请选择试题图片或 PDF 文件。');state.archivePromise=window.MytreeUploads?.save(file);let data=await readFile(file);if(epoch!==state.photoEpoch)return;if(state.fileKind==='pdf'){data='data:application/pdf;base64,'+data.split(',')[1];state.documentData=data;const result=await post('/api/files/preview',{file_data:data,page:1},30000);if(epoch!==state.photoEpoch)return;state.pageCount=result.page_count;await loadPreview(result.preview,epoch);}else await loadPreview(data,epoch);
 }catch(e){if(epoch===state.photoEpoch)state.sourceError=e.message;}finally{if(epoch===state.photoEpoch){state.sourceLoading=false;renderSource();}}
}
async function selectPage(page){if(!state.documentData||state.sourceLoading||page===state.page)return;cropPointers.clear();cropGesture=null;multiPan=null;multiGesture=false;const epoch=++state.photoEpoch;resetRecognition();state.sourceLoading=true;state.sourceError='';state.ocrBusy=false;renderSource();try{const result=await post('/api/files/preview',{file_data:state.documentData,page},30000);if(epoch!==state.photoEpoch)return;state.page=result.page;state.pageCount=result.page_count;await loadPreview(result.preview,epoch);}catch(e){if(epoch===state.photoEpoch)state.sourceError=e.message;}finally{if(epoch===state.photoEpoch){state.sourceLoading=false;renderSource();}}}
function toggleCrop(){if(!state.sourceImage)return;if(!state.cropMode){state.cropMode=true;const image=state.sourceImage;state.dragBox=state.cropBox||{x:image.naturalWidth*.1,y:image.naturalHeight*.1,w:image.naturalWidth*.8,h:image.naturalHeight*.4};renderSource();$('source-canvas').focus();return;}const rect=state.dragBox;if(!rect||rect.w<32||rect.h<32){$('crop-help').textContent='选区太小，请把完整题目和作答都框进来。';return;}const canvas=document.createElement('canvas');canvas.width=Math.round(rect.w);canvas.height=Math.round(rect.h);canvas.getContext('2d').drawImage(state.sourceImage,rect.x,rect.y,rect.w,rect.h,0,0,canvas.width,canvas.height);state.photoData=canvas.toDataURL('image/jpeg',.9);state.cropBox={...rect};state.cropMode=false;state.photoEpoch++;resetRecognition();const preview=$('source-canvas')?.parentElement,scroll=preview?{top:preview.scrollTop,left:preview.scrollLeft}:null;renderSource();if(scroll){const next=$('source-canvas')?.parentElement;if(next){next.scrollTop=scroll.top;next.scrollLeft=scroll.left;}}}
async function resetCrop(){if(!state.photo)return;state.cropMode=false;state.cropBox=null;state.dragBox=null;state.photoEpoch++;resetRecognition();await loadPreview(state.photo,state.photoEpoch);renderSource();}
function canvasPoint(event){const rect=$('source-canvas').getBoundingClientRect();return{x:Math.max(0,Math.min(state.sourceImage.naturalWidth,(event.clientX-rect.left)*state.sourceImage.naturalWidth/rect.width)),y:Math.max(0,Math.min(state.sourceImage.naturalHeight,(event.clientY-rect.top)*state.sourceImage.naturalHeight/rect.height))};}
const cropPointers=new Map();let cropGesture=null,multiPan=null,multiGesture=false;
function cancelDrag(){cropGesture=null;state.cropMode=false;state.dragBox=null;paintPreview();updateRecognitionButton();}
function midpoint(){const points=[...cropPointers.values()];return {x:points.reduce((n,p)=>n+p.x,0)/points.length,y:points.reduce((n,p)=>n+p.y,0)/points.length};}
document.addEventListener('pointerdown',event=>{
 if(event.target.id!=='source-canvas'||!state.sourceImage||state.ocrBusy||state.sourceLoading||event.button>0)return;
 event.preventDefault();event.target.setPointerCapture(event.pointerId);cropPointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
 if(cropPointers.size>1){multiGesture=true;cancelDrag();const center=midpoint(),preview=event.target.parentElement;multiPan={...center,top:preview.scrollTop,left:preview.scrollLeft};return;}
 multiGesture=false;state.cropMode=true;state.dragBox=null;updateRecognitionButton();cropGesture={id:event.pointerId,start:canvasPoint(event),x:event.clientX,y:event.clientY,moved:false};paintPreview();
});
document.addEventListener('pointermove',event=>{
 if(!cropPointers.has(event.pointerId))return;cropPointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
 if(multiGesture){if(cropPointers.size>1&&multiPan){const center=midpoint(),preview=event.target.parentElement;preview.scrollTop=multiPan.top+multiPan.y-center.y;preview.scrollLeft=multiPan.left+multiPan.x-center.x;}return;}
 if(!cropGesture||event.target.id!=='source-canvas')return;
 if(Math.hypot(event.clientX-cropGesture.x,event.clientY-cropGesture.y)<5&&!cropGesture.moved)return;
 cropGesture.moved=true;const preview=event.target.parentElement,bounds=preview.getBoundingClientRect();if(event.clientY>bounds.bottom-22)preview.scrollTop+=12;else if(event.clientY<bounds.top+22)preview.scrollTop-=12;
 const p=canvasPoint(event),start=cropGesture.start;state.dragBox={x:Math.min(p.x,start.x),y:Math.min(p.y,start.y),w:Math.abs(p.x-start.x),h:Math.abs(p.y-start.y)};paintPreview();
});
function endPointer(event,cancelled=false){if(!cropPointers.has(event.pointerId))return;cropPointers.delete(event.pointerId);if(multiGesture){if(!cropPointers.size){multiGesture=false;multiPan=null;}return;}
 const gesture=cropGesture;cropGesture=null;if(!cancelled&&gesture?.moved&&state.dragBox?.w>=32&&state.dragBox?.h>=32)toggleCrop();else cancelDrag();
}
document.addEventListener('pointerup',event=>endPointer(event));document.addEventListener('pointercancel',event=>endPointer(event,true));
document.addEventListener('dblclick',event=>{if(event.target.id==='source-canvas'&&!state.ocrBusy){event.preventDefault();resetCrop();}});
document.addEventListener('keydown',event=>{
 if(event.target.id!=='source-canvas'||!state.sourceImage||state.ocrBusy)return;
 const preview=event.target.parentElement;
 if(['PageDown','PageUp','Home','End'].includes(event.key)){event.preventDefault();if(event.key==='Home'){preview.scrollTop=0;preview.scrollLeft=0;}else if(event.key==='End')preview.scrollTop=preview.scrollHeight;else preview.scrollTop+=(event.key==='PageDown'?1:-1)*preview.clientHeight*.7;return;}
 if(event.altKey&&event.key.startsWith('Arrow')){event.preventDefault();preview.scrollLeft+=event.key==='ArrowRight'?40:event.key==='ArrowLeft'?-40:0;preview.scrollTop+=event.key==='ArrowDown'?40:event.key==='ArrowUp'?-40:0;return;}
 if(event.key==='Escape'){event.preventDefault();if(state.cropMode)cancelDrag();else resetCrop();return;}
 if(event.key==='Enter'){if(state.cropMode){event.preventDefault();toggleCrop();}return;}
 if(!event.key.startsWith('Arrow'))return;event.preventDefault();const image=state.sourceImage;
 if(!state.cropMode){state.cropMode=true;state.dragBox={...(state.cropBox||{x:image.naturalWidth*.1,y:image.naturalHeight*.1,w:image.naturalWidth*.6,h:image.naturalHeight*.3})};}
 updateRecognitionButton();const r=state.dragBox,dx=image.naturalWidth*.02,dy=image.naturalHeight*.02;
 if(event.shiftKey){if(event.key==='ArrowRight')r.w+=dx;if(event.key==='ArrowLeft')r.w-=dx;if(event.key==='ArrowDown')r.h+=dy;if(event.key==='ArrowUp')r.h-=dy;r.w=Math.max(32,Math.min(r.w,image.naturalWidth-r.x));r.h=Math.max(32,Math.min(r.h,image.naturalHeight-r.y));}
 else{if(event.key==='ArrowRight')r.x+=dx;if(event.key==='ArrowLeft')r.x-=dx;if(event.key==='ArrowDown')r.y+=dy;if(event.key==='ArrowUp')r.y-=dy;r.x=Math.max(0,Math.min(r.x,image.naturalWidth-r.w));r.y=Math.max(0,Math.min(r.y,image.naturalHeight-r.h));}paintPreview();
});
document.addEventListener('click',event=>{if(event.target.closest('[data-retry-page]'))recognizePhoto();});
async function recognizePhoto(){
 if(!state.photoData||state.ocrBusy||state.cropMode)return;
 const epoch=state.photoEpoch;if(state.pageBatch){if(state.batchBusy)return;state.stage='batch';state.showOriginal=false;syncStage();await organizePage(epoch,state.pageBatch);openPageReading(state.activeReadingId||state.pageBatch.items[0]?.reading_id);return;}if(!state.pageRequestId){state.pageRequestId=requestId();state.sourceGeneration=requestId();}state.ocrBusy=true;updateRecognitionButton();
 const output=$('recognition-message');output.innerHTML=notice('正在识别这一页的题目和原样作答，无需逐题校准…');
 try{
  const archivePromise=state.archivePromise;const result=await post('/api/recognize/page',{image_data:state.photoData,request_id:state.pageRequestId,client_generation:state.sourceGeneration,page_index:state.fileKind==='pdf'?state.page:1},150000);
  if(epoch!==state.photoEpoch||result.client_generation!==state.sourceGeneration)return;
  window.MytreeUploads?.link(archivePromise,result).catch(()=>{});state.pageBatch=result;state.pageStudies={};state.batchCancelled=false;state.stage='batch';output.innerHTML='';renderPageItems();syncStage();
  $('recognition-review').scrollIntoView({block:'start',behavior:'auto'});await organizePage(epoch,result);
 }catch(error){if(epoch===state.photoEpoch&&output.isConnected){output.innerHTML=notice(error.message,'error')+'<button type="button" class="ghost small" data-retry-page>重试识别</button><span class="field-tip">原图和已有结果仍保留，也可以重新拍照。</span>';if(error.message.includes('过期')||error.message.includes('取消')){state.pageRequestId=requestId();state.sourceGeneration=requestId();}}}
 finally{if(epoch===state.photoEpoch){state.ocrBusy=false;updateRecognitionButton();}}
}
function bankContent(value){
 if(!value)return '';
 return `<div class="math-prose">${richHTML(value.text,true)}</div>${value.images.map(url=>`<img class="bank-image" src="${esc(url)}" alt="题库提供的图形或公式，尚未核对" loading="lazy" referrerpolicy="no-referrer">`).join('')}`;
}
function questionBankHTML(item){
 const found=state.questionSearch[item.reading_id];
 const button=`<button class="ghost small" data-search-question="${esc(item.reading_id)}" ${found?.status==='loading'?'disabled':''}>${found?.status==='loading'?'正在找题库候选…':found?'重新查看题库':'找原题'}</button>`;
 if(!found||found.status==='loading')return `<div class="question-bank">${button}</div>`;
 return `<section class="question-bank">${button}<p class="field-tip" role="status">${esc(found.message)}</p>${(found.candidates||[]).map(candidate=>`<details class="bank-candidate"><summary>题库候选 · ${candidate.comparison==='text_equal'?'文字相同，仍未核对':candidate.comparison==='incomplete_or_unchecked'?'含图片，需核对完整条件':'相关题，未确认是原题'}</summary><p class="field-tip">${esc(candidate.provider_name)} · 题库编号 ${esc(candidate.provider_item_id)}</p>${bankContent(candidate.content)}${candidate.content.has_images?'<p class="field-tip">此候选含图片或公式图片，尚未展开，不能确认完整原题。</p>':''}</details>`).join('')}${found.queried_at?`<p class="field-tip">查询时间：${esc(new Date(found.queried_at).toLocaleString())}${found.cached?' · 使用缓存':''}</p>`:''}</section>`;
}
async function searchQuestion(id){
 const batch=state.pageBatch,item=batch?.items.find(value=>value.reading_id===id);if(!item||state.questionSearch[id]?.status==='loading')return;
 const epoch=state.photoEpoch;state.questionSearch[id]={status:'loading'};renderPageItems();
 try{
  const result=await post('/api/questions/search',{batch_id:batch.batch_id,reading_id:id,source_revision:batch.source_revision,request_id:requestId()},25000);
  if(epoch===state.photoEpoch&&batch.batch_id===state.pageBatch?.batch_id)state.questionSearch[id]=result;
 }catch(error){if(epoch===state.photoEpoch&&batch.batch_id===state.pageBatch?.batch_id)state.questionSearch[id]={status:'failed',message:error.message};}
 finally{if(epoch===state.photoEpoch)renderPageItems();}
}
function renderPageItems(){
 const batch=state.pageBatch,box=$('recognition-review');if(!batch||!box)return;
 const completed=Object.values(state.pageStudies).filter(s=>s.status==='done').length;
 const blocked=batch.items.filter(i=>!i.auto_ready&&!i.lesson_ready).length;
 box.innerHTML=`<section class="page-items"><div class="section-title"><div><span class="source-tag">整页识别 · 无需逐题校准</span><h2>已整理 ${completed} 题${blocked?'，'+blocked+' 题先跳过':''}</h2><p class="field-tip">共读到 ${batch.items.length} 道大题。学生原作答保留，数学核验状态逐题显示。</p></div>${state.batchBusy?'<button class="ghost small" id="stop-page-work">停止后续整理</button>':''}</div>${batch.warnings.map(v=>notice(v)).join('')}${state.batchCancelled?notice('已停止尚未开始的整理，完成的题仍保留。可以继续整理未完成的题。')+`<button class="ghost small" id="resume-page-work" ${state.batchInFlight?'disabled':''}>${state.batchInFlight?'等待当前题完成…':'继续未完成的整理'}</button>`:''}<div class="page-item-list">${batch.items.map((item,index)=>{
 const study=state.pageStudies[item.reading_id];const label=study?.status==='done'?'已整理':study?.status==='running'?'正在整理…':state.batchCancelled&&(item.auto_ready||item.lesson_ready)?'已停止':study?.status==='failed'?'整理失败，可重试':!item.auto_ready&&!item.lesson_ready?'先跳过这题':'等待整理';
 return `<article class="page-item ${state.activeReadingId===item.reading_id?'selected':''}" data-page-item="${esc(item.reading_id)}"><div class="section-title"><strong>第 ${index+1} 题${item.printed_number?' · 题号 '+esc(item.printed_number):''}</strong><span class="source-tag">${label}</span></div><div class="math-prose">${richHTML(item.problem||'题干尚未读完整，请查看已识别片段。',true)}</div><button class="ghost small" data-open-reading="${esc(item.reading_id)}">${study?.status==='done'?'打开这题':'查看已识别内容'}</button>${!item.auto_ready&&!item.lesson_ready?`<p class="field-tip">${esc(item.attention_reasons.join(' ')||'当前题型暂不支持。')}</p><button class="ghost small" data-retake-reading="${esc(item.reading_id)}">重拍这题</button>`:study?.status==='failed'&&!state.batchCancelled?`${notice(study.error,'error')}<button class="ghost small" data-retry-reading="${esc(item.reading_id)}">只重试这题</button>`:''}</article>`;
 }).join('')}</div>${batch.unassigned_fragments.length?`<details class="study-details"><summary>有 ${batch.unassigned_fragments.length} 处笔迹暂未归属</summary><p class="field-tip">这些内容未混入其他题目，相关题先跳过。</p>${batch.unassigned_fragments.map(f=>`<div class="math-prose">${richHTML(f.text,true)}</div>`).join('')}</details>`:''}</section>`;
 box.classList.remove('hidden');
}
function changeRecognizedQuestion(direction){
 const items=state.pageBatch?.items||[],index=items.findIndex(i=>i.reading_id===state.activeReadingId);
 for(let n=index+direction;n>=0&&n<items.length;n+=direction){if(state.pageStudies[items[n].reading_id]?.status==='done'){document.querySelector('dialog[data-reading-chooser][open]')?.close();openPageReading(items[n].reading_id);return;}}
}
let questionSwipe=null;
document.addEventListener('touchstart',event=>{const target=event.target.closest('#result .current-question,dialog[data-reading-chooser] .page-item-list');questionSwipe=target&&event.touches.length===1?{x:event.touches[0].clientX,y:event.touches[0].clientY,at:Date.now(),target}:null;},{passive:true});
document.addEventListener('touchend',event=>{const start=questionSwipe;questionSwipe=null;if(!start||!event.changedTouches.length)return;const p=event.changedTouches[0],dx=p.clientX-start.x,dy=p.clientY-start.y;if(Date.now()-start.at<1200&&Math.abs(dx)>50&&Math.abs(dx)>Math.abs(dy)*1.6){if(start.target.matches('.page-item-list')){const buttons=start.target.querySelectorAll(':scope > .focus-pager button');const button=buttons[dx<0?1:0];if(button&&!button.disabled)button.click();}else changeRecognizedQuestion(dx<0?1:-1);}},{passive:true});
document.addEventListener('mytree:select-question',event=>{if(typeof event.detail?.readingId==='string')openPageReading(event.detail.readingId);});
function originalWorkHTML(item){
 const lines=item.steps||[],presence=item.answer_presence;
 return `<details class="study-details"><summary>我的作答</summary>${lines.length?lines.map((line,i)=>`<div class="step unknown"><span class="n">${i+1}</span><div class="math-prose">${richHTML(line)}</div><span class="status">—</span></div>`).join(''):`<p>${presence==='absent'?'原图中未发现作答。':presence==='present'?'检测到作答，但文字未读完整。':'作答区域尚未读清，暂不能确定内容。'}</p>`}</details>`;
}
function openPageReading(id){
 const study=state.pageStudies[id],item=state.pageBatch?.items.find(i=>i.reading_id===id);if(!item)return;
 state.activeReadingId=id;state.ocrResult=item;state.problem=item.problem;state.steps=item.steps.join('\n');state.hintLevel=1;state.tutorMessages=[];state.exercises=[];state.stage='learn';state.showOriginal=false;
 if(study?.status==='done'){state.previewReading=null;state.result=study.value;if($('result'))$('result').innerHTML=renderDiagnosis(study.value);}
 else{state.previewReading=item;state.result=null;const fragments=(item.fragments||[]).filter(f=>f.role!=='teacher_annotation'&&f.role!=='crossed_out');
  $('result').innerHTML=`<div class="current-question math-prose">${richHTML(item.problem||'题干尚未读完整。')}</div><span class="source-tag">已识别内容 · 尚未核验</span>${notice((item.attention_reasons||[]).join(' ')||'正在整理这道题；以下是目前已识别的内容。')}<section class="partial-transcript"><h3>已识别片段</h3>${fragments.map(f=>`<p class="field-tip">${f.role==='student_work'?'原作答片段':f.role==='problem'?'题干片段':'未确定归属的片段'}</p><div class="math-prose">${richHTML(f.text)}</div>`).join('')||'<p>尚无其他清晰片段。</p>'}<p class="field-tip">条件未完整时只展示识别内容，不据此自动判题。</p><button class="ghost small" data-retake-reading="${esc(item.reading_id)}">重新识别这页</button></section>${originalWorkHTML(item)}`;
 }
 renderPageItems();syncStage();
}
async function organizeReading(item,epoch,batch){
 if(state.batchCancelled||epoch!==state.photoEpoch)return;
 state.batchInFlight++;state.pageStudies[item.reading_id]={status:'running'};renderPageItems();
 try{
  const value=await post('/api/study/reading',{batch_id:batch.batch_id,source_revision:batch.source_revision,reading_id:item.reading_id,request_id:requestId()},150000);
  if(epoch!==state.photoEpoch||batch.batch_id!==state.pageBatch?.batch_id)return;
  state.pageStudies[item.reading_id]={status:'done',value};if(!state.activeReadingId||state.previewReading?.reading_id===item.reading_id)openPageReading(item.reading_id);
 }catch(error){if(epoch===state.photoEpoch&&batch.batch_id===state.pageBatch?.batch_id)state.pageStudies[item.reading_id]={status:'failed',error:error.message};}
 finally{if(epoch===state.photoEpoch){state.batchInFlight=Math.max(0,state.batchInFlight-1);renderPageItems();syncStage();}}
}
async function organizePage(epoch,batch){
 state.batchBusy=true;renderPageItems();const ready=batch.items.filter(i=>(i.auto_ready||i.lesson_ready)&&state.pageStudies[i.reading_id]?.status!=='done');let next=0;
 const worker=async()=>{while(next<ready.length&&!state.batchCancelled&&epoch===state.photoEpoch){const item=ready[next++];await organizeReading(item,epoch,batch);}};
 await Promise.all([worker(),worker()]);
 if(epoch===state.photoEpoch){state.batchBusy=false;renderPageItems();if(!state.activeReadingId&&batch.items.length)openPageReading(batch.items[0].reading_id);refreshSidebar();syncStage();}
}
function readingChoicesHTML(result){
 if(!result.alternatives?.length)return '';
 const groups=Object.groupBy?Object.groupBy(result.alternatives,item=>item.group):result.alternatives.reduce((all,item)=>{(all[item.group]??=[]).push(item);return all;},{});
 return `<section class="reading-choices"><h3>核对不清楚的位置</h3>${result.inferred?'<span class="source-tag">按我的读法 · 可以更改</span>':''}<div class="math-prose">${richHTML(result.reading_evidence||'请从下面选择你实际写的内容。')}</div>${Object.values(groups).map(items=>`<div class="reading-group"><p class="field-tip">${items[0].line===0?'题干':`第 ${items[0].line} 行作答`}</p>${items.map(item=>`<div class="reading-option"><div class="math-prose">${richHTML(item.text,true)}</div><p class="field-tip">${item.consistency==='match'?'与你写的其他内容一致':item.consistency==='conflict'?'与你后面写的内容矛盾':'没有其他线索'}</p><button class="ghost small" data-reading-choice="${esc(item.id)}" ${item.selected?'disabled':''}>${item.selected?'当前读法':'改用这个读法'}</button></div>`).join('')}</div>`).join('')}</section>`;
}
function selectReading(id){
 const reading=state.ocrResult;if(!reading)return;const candidate=reading.alternatives.find(item=>item.id===id);if(!candidate)return;
 if(candidate.line===0){state.problem=candidate.text;reading.problem=candidate.text;reading.problem_latex='';}
 else reading.steps[candidate.line-1]=candidate.text;
 reading.alternatives=reading.alternatives.map(item=>item.group===candidate.group?{...item,selected:item.id===id}:item);
 reading.inferred=false;reading.reading_evidence='你已选择这个读法。确认后，按你核对的内容检查。';
 state.steps=reading.steps.join('\n');state.result=null;state.exercises=[];state.ocrPending=true;state.stage='review';
 if($('result'))$('result').innerHTML='';showRecognitionConfirmation(reading);
 if($('recognition-message'))$('recognition-message').innerHTML=notice('读法已更改，请重新确认。');
}
function cardNoteHTML(card){
 if(!card)return '';
 return `<section class="saved-card" data-card-id="${esc(card.id)}"><span class="source-tag">${['wrong_step','incomplete'].includes(card.study_status)?'错题卡':'学习卡'} · 已保存</span><details class="note-editor"><summary>笔记</summary><textarea id="learner-note" maxlength="3000" placeholder="可以记一句自己的想法">${esc(card.learner_note||'')}</textarea><button class="ghost small" id="save-card-note">保存我的笔记</button><div id="card-note-status" aria-live="polite"></div></details>${learning.cardActions(card)}</section>`;
}
async function saveCardNote(){
 const card=state.result?.wrong_card;if(!card)return;const button=$('save-card-note'),output=$('card-note-status');button.disabled=true;
 try{const result=await post('/api/cards/edit',{card_id:card.id,expected_revision:card.revision,learner_note:$('learner-note').value,request_id:requestId()});state.result.wrong_card=result.card;output.innerHTML=notice('笔记已保存，下次回来还在。','success');}
 catch(error){output.innerHTML=notice(error.message,'error');}finally{button.disabled=false;}
}
function showRecognitionConfirmation(result){
 const box=$('recognition-review');if(!box)return;box.classList.remove('hidden');
 const uncertain=result.uncertain_lines.length?'重点核对：'+result.uncertain_lines.map(n=>n===0?'题干':`第 ${n} 行作答`).join('、')+'。':'请对照原图核对条件、正负号、根号和括号。';
 const pure=result.problem_latex;
 const stripPrefix=source=>source.replace(/^(?:(?:原式|解|得|所以|因此)|[\s:：=])+/,'');
 const simple=source=>{const v=stripPrefix(source);return !/[\u3400-\u9fff]/.test(v)&&(!/[\\$]/.test(v)||/^\\\([\s\S]*\\\)$/.test(v)||(!v.includes('\\(')&&!v.includes('$')));};
 box.innerHTML=`<section class="recognition-review"><span class="source-tag">AI 识别结果 · 请核对</span><h2>确认读到的内容</h2><p class="field-tip">${esc(uncertain)}</p>${result.warnings.length?`<div class="notice math-prose">${richHTML(result.warnings.join('；'),true)}</div>`:''}${readingChoicesHTML(result)}<label>识别出的题干</label>${pure?`<div class="question-paper math-prose" data-edit-preview="problem-math">${mathHTML(pure)}</div><details class="correction line-editor"><summary>修改题干公式</summary>${mathField(pure,'id="problem-math" aria-label="核对题干公式"')}<button class="ghost small" data-finish-edit>完成修改</button><button class="ghost small" data-cancel-edit>取消修改</button></details>`:`<div id="problem-preview" data-edit-preview="problem-source" class="question-paper math-prose">${richHTML(state.problem,true)}</div><details class="correction line-editor"><summary>修改题干文字</summary><label for="problem-source">仅用于校正识别，公式保留数学排版标记</label><textarea id="problem-source" maxlength="6000">${esc(state.problem)}</textarea><button class="ghost small" id="preview-correction" data-finish-edit>完成修改</button><button class="ghost small" data-cancel-edit>取消修改</button></details>`}
 ${result.steps.length?`<label>识别出的作答步骤</label><div class="ocr-steps">${result.steps.map((line,i)=>simple(line)?`<div class="question-paper math-prose" data-edit-preview="ocr-step-${i}"><span class="step-label">第 ${i+1} 行</span>${richHTML(line,true)}</div><details class="correction line-editor"><summary>修改第 ${i+1} 行</summary>${mathField(stripPrefix(line),`id="ocr-step-${i}" data-step-source aria-label="核对第 ${i+1} 行作答"`)}<button class="ghost small" data-finish-edit>完成修改</button><button class="ghost small" data-cancel-edit>取消修改</button></details>`:`<div class="question-paper math-prose" data-edit-preview="ocr-step-${i}">${richHTML(line,true)}</div><details class="correction line-editor"><summary>修改第 ${i+1} 行文字</summary><textarea id="ocr-step-${i}" data-step-source aria-label="校正第 ${i+1} 行文字" maxlength="1500">${esc(line)}</textarea><button class="ghost small" data-finish-edit>完成修改</button><button class="ghost small" data-cancel-edit>取消修改</button></details>`).join('')}</div><p class="field-tip">需要校正时，点对应行的“修改”。</p>`:notice('没有读到作答。确认后先看讲解，不会记为错题。')}
 <button id="confirm-ocr" class="full">确认并开始学习</button></section>`;
 syncStage();
}
async function toggleHint(button){
 const n=Number(button.dataset.hint),box=$('hint-'+n);
 if(button.getAttribute('aria-expanded')==='true'){button.setAttribute('aria-expanded','false');box.classList.add('hidden');return;}
 button.disabled=true;
 try{const result=await post('/api/hint',{diagnosis_id:state.result.diagnosis_id,level:n+1});
 state.hintLevel=Math.max(state.hintLevel,result.max_hint_level_recorded);state.result.analysis.hints[n]=result.text;
 box.innerHTML=richHTML(result.text,state.result.analysis.engine!=='junior');box.classList.remove('hidden');button.setAttribute('aria-expanded','true');
 const next=document.querySelector(`[data-hint="${n+1}"]`);button.classList.remove('primary-next');if(next){next.disabled=false;next.classList.add('primary-next');next.closest('.hint-block').classList.remove('hidden');}
 }catch(error){box.innerHTML=notice(error.message+' 可再次点击重试。','error');box.classList.remove('hidden');}
 finally{button.disabled=false;}
}
async function recordFeedback(button){
 if(!state.result?.diagnosis_id)return;const output=$('feedback-status');button.disabled=true;
 try{const result=await post('/api/feedback',{diagnosis_id:state.result.diagnosis_id,rating:button.dataset.rating});output.innerHTML=notice(button.dataset.rating==='incorrect'?'已标记为待核对。反馈不会自动改动数学答案或评分规则。':result.message,'success');
 if(button.dataset.rating==='confusing')await askTutor('我还没理解，请用一个具体例子，短一点解释，一次只问一个问题。');
 }catch(error){output.innerHTML=notice(error.message,'error');}finally{button.disabled=false;}
}

async function askTutor(question) {
 const form=$('tutor-form');const output=$('tutor-status');if(!form||!state.result?.diagnosis_id)return;
 question=(question??$('tutor-question').value).trim();if(!question){output.innerHTML=notice('先写下你想问的一个问题。','error');return;}
 const diagnosisId=state.result.diagnosis_id;const history=state.tutorMessages.slice(-6).map(t=>({role:t.role,content:t.content}));const buttons=[...form.querySelectorAll('button'),...document.querySelectorAll('[data-tutor-prompt]')];buttons.forEach(b=>b.disabled=true);output.innerHTML=notice('正在结合这道题组织讲解…');
 try {const result=await post('/api/chat',{diagnosis_id:diagnosisId,question,level:state.hintLevel,history},95000);if(diagnosisId!==state.result?.diagnosis_id||!output.isConnected)return;
 state.tutorMessages.push({role:'user',content:question},{role:'assistant',content:result.reply,equations:result.equations,fallback:result.fallback});state.tutorMessages=state.tutorMessages.slice(-10);$('tutor-messages').innerHTML=renderTutorMessages();$('tutor-question').value='';output.innerHTML='';
 }catch(e){if(output.isConnected)output.innerHTML=notice(e.message+' 仍然可以展开上方的分级提示。','error');}
 finally{buttons.forEach(b=>b.disabled=false);}
}

async function renderTree(version){return learning.renderTree(()=>version===renderVersion);}
async function renderPlan(version) {
 app.innerHTML=intro('温故，也知新','每天，向前一小步。','按你的空闲时段安排复习，一次约 5 分钟。所有时间均为北京时间。')+'<div id="plan-content" role="status">正在读取复习安排…</div>';
 try{const [data,today]=await Promise.all([getProfile(),api('/api/review/today')]);if(version!==renderVersion)return;
 const reasons=new Map(today.items.map(item=>[item.id,item.reason]));
 $('plan-content').innerHTML=`<div class="two-col"><section class="panel"><div class="panel-heading"><span class="number">01</span><h2>下一次复习</h2></div><button class="ghost small" id="personalize-plan">更新个性化复习</button><p id="plan-memory-status" role="status"></p>${data.reviews.length?data.reviews.map(r=>`<div class="review-line"><div><strong>${esc(r.title)}</strong><small>${formatTime(r.due)} · 已完成 ${r.completed} 轮</small>${reasons.has(r.id)?`<p>${esc(reasons.get(r.id))}</p>`:""}</div><button class="ghost small" data-review="${esc(r.id)}">现在练习</button></div>`).join(''):'<div class="empty"><p>还没有要复习的卡点。</p><a href="/" data-nav="/">先检查一道题 →</a></div>'}<p class="field-tip">发现卡点后先隔 1 天；每完成一组，再按 3 天、7 天安排到下一个空闲日。也可以提前练习。</p></section><section class="panel"><div class="panel-heading"><span class="number">02</span><h2>我的空闲时间</h2></div><p class="small-text muted">哪几天，适合留一点时间给数学？</p><form id="availability"><div class="days">${['一','二','三','四','五','六','日'].map((day,i)=>`<label>周${day}<input type="checkbox" name="day" value="${i+1}" ${data.availability.days.includes(i+1)?'checked':''}></label>`).join('')}</div><label for="free-time">开始时间（北京时间）</label><input id="free-time" type="time" value="${esc(data.availability.time)}" required style="margin:7px 0 16px"><button class="full" type="submit">保存空闲时间</button><div id="save-message" aria-live="polite"></div></form></section></div><section class="panel" style="margin-top:24px"><h2>今天，继续练一练</h2>${data.pending.length?`<p class="small-text muted">还有 ${data.pending.length} 道练习没有完成，进度已经保存。</p><button class="ghost" id="resume-practice">继续上次练习 →</button>`:'<p class="small-text muted">从上方选择一个知识点，开始这次练习。</p>'}<div id="practice-list" class="practice-list" aria-live="polite"></div></section>`;
 $('personalize-plan').onclick=async()=>{const button=$('personalize-plan');button.disabled=true;$('plan-memory-status').textContent='正在读取历史作答…';try{const result=await post('/api/review/personalize',{},90000);await render();$('plan-memory-status').textContent=(result.memory.engine==='mem0'?'长期学习记忆已更新。':'')+result.message;}catch(error){$('plan-memory-status').textContent=error.message;button.disabled=false;}};
 if($('resume-practice')) $('resume-practice').onclick=()=>{state.exercises=data.pending;$('practice-list').innerHTML=exerciseHTML(data.pending);};
 $('availability').onsubmit=async event=>{event.preventDefault();const button=$('availability').querySelector('button');const output=$('save-message');const availability={days:[...document.querySelectorAll('input[name=day]:checked')].map(e=>Number(e.value)),time:$('free-time').value};button.disabled=true;try{await post('/api/availability',{availability});await render();if($('save-message'))$('save-message').innerHTML=notice('已保存','success');}catch(e){output.innerHTML=notice(e.message,'error');button.disabled=false;}};
 }catch(e){if(version===renderVersion)$('plan-content').innerHTML=notice(e.message,'error')+'<button class="ghost retry" data-reload>重新读取</button>';}
}
async function renderParent(version) {
 app.innerHTML=intro('GROWING, ONE STEP AT A TIME','看见孩子，正在学会什么。','关注具体卡点和下一步安排，比一次对错更有帮助。')+notice('这是当前浏览器的演示学习档案，尚未建立家长账号与授权绑定。请用自编题体验，不录入孩子的姓名、学校等信息。')+'<div id="parent-content" role="status">正在整理学习记录…</div>';
 try{const data=await getProfile();if(version!==renderVersion)return;
 const entries=Object.entries(data.causes).sort((a,b)=>b[1]-a[1]);const max=Math.max(1,...entries.map(e=>e[1]));
 $('parent-content').innerHTML=`<div class="stats"><div class="stat"><strong>${data.history}</strong><span>累计作答检查</span></div><div class="stat"><strong>${data.practice_correct}</strong><span>针对练习做对</span></div><div class="stat"><strong>${data.tree.filter(k=>k.lit).length}</strong><span>知识点初次点亮</span></div></div><div class="two-col"><section class="panel"><h2>卡在哪些地方</h2>${entries.length?entries.map(([key,value])=>`<div class="chart-bar"><span>${esc(names[key]||key)}</span><i style="width:${Math.round(value/max*100)}%"></i><span>${value} 次</span></div>`).join(''):'<p class="empty">还没有卡点记录，检查一道题后会出现在这里。</p>'}<p class="field-tip">这是历史诊断次数，不是对孩子的能力评定。</p></section><section class="panel"><h2>下一步，怎么陪孩子</h2>${data.reviews.length?data.reviews.slice(0,4).map(r=>`<div class="review-line"><div>${esc(r.title)}<small>${formatTime(r.due)} · 已练 ${r.completed} 轮</small></div><a href="/plan" data-nav="/plan">查看</a></div>`).join(''):'<p class="empty">完成诊断后，这里会显示具体的复习安排。</p>'}<p class="field-tip">可以问一句：“这次你是怎么想的？”让孩子自己说说步骤。</p></section></div><section class="panel" style="margin-top:24px"><h2>最近的学习记录</h2>${data.recent.length?data.recent.map(e=>`<div class="event"><small>${formatTime(e.at)}</small><div><span class="source-tag">${e.type==='lesson'?'新题学习':e.type==='practice'?'针对练习':'作答检查'}</span><div class="formula">${richHTML(e.problem,true)}</div></div><span>${e.status==='not_attempted'?'待作答':e.status==='correct'?'已做对':e.status==='incomplete'?'待做完':e.status==='ai_review'?'待核对':'有卡点'}</span></div>`).join(''):'<p class="empty">还没有学习记录。<a href="/" data-nav="/">回到学习桌开始 →</a></p>'}</section>`;
 }catch(e){if(version===renderVersion)$('parent-content').innerHTML=notice(e.message,'error')+'<button class="ghost retry" data-reload>重新读取</button>';}
}
async function render() {
 diagramController.close();
 document.body.dataset.route=location.pathname;app.classList.remove('source-view');
 const version = ++renderVersion; const path=location.pathname;
 if(path!=='/'&&state.batchBusy)cancelPageWork();
 if(explorerController){explorerController.destroy();explorerController=null;}
 document.querySelectorAll('nav [data-nav]').forEach(a=>{if(a.dataset.nav===path)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
 if(path==='/explore'){document.title='探索者 · 小树同学';explorerController=Explorer.mount({app,student,navigate:path=>{history.pushState({},'',path);render();window.scrollTo(0,0);}});return;}
 document.title=({'/':'学习桌','/tree':'知识树','/plan':'复习计划','/parent':'家长看板'}[path]||'学习桌')+' · 小树同学';
 if(path==='/tree')return renderTree(version);if(path==='/plan')return renderPlan(version);if(path==='/parent')return renderParent(version);return renderStudent(version);
}
document.addEventListener('click',event=>{
 const editorSummary=event.target.closest('.line-editor > summary');
 if(editorSummary){const detail=editorSummary.parentElement;if(!detail.open)detail.dataset.original=detail.querySelector('math-field,textarea')?.value??'';}
 const link=event.target.closest('a[data-nav]');if(link&&!event.metaKey&&!event.ctrlKey){event.preventDefault();history.pushState({},'',link.getAttribute('href'));render();window.scrollTo(0,0);return;}
 const button=event.target.closest('button');if(!button||button.disabled)return;
 if(button.id==='open-camera')$('camera-input').click();
 if(button.id==='open-file')$('file-input').click();
 if(button.id==='replace-file')$('file-input').click();
 if(button.id==='retake-photo')$('camera-input').click();
 if(button.id==='close-source'){state.photoEpoch++;resetRecognition();state.fileName='';state.photoData=null;state.photo=null;state.sourceImage=null;state.documentData=null;cropPointers.clear();cropGesture=null;multiPan=null;multiGesture=false;renderSource();}
 if(button.id==='back-to-source'){state.stage='select';state.showOriginal=false;syncStage();}
 if(button.id==='view-original'){state.showOriginal=!state.showOriginal;syncStage();}
 if(button.hasAttribute('data-finish-edit')||button.hasAttribute('data-cancel-edit')){
  const detail=button.closest('details'),input=detail?.querySelector('math-field,textarea');
  if(input&&button.hasAttribute('data-cancel-edit'))input.value=detail.dataset.original??input.value;
  if(input){const preview=document.querySelector(`[data-edit-preview="${input.id}"]`);if(preview)preview.innerHTML=input.tagName==='MATH-FIELD'?mathHTML(input.value):richHTML(input.value,true);}
  if(detail){detail.open=false;detail.querySelector('math-field')?.blur();window.mathVirtualKeyboard?.hide();}
 }
 if(button.id==='recognize-photo')recognizePhoto();
 if(button.id==='resume-page-work'){
  const batch=state.pageBatch;button.disabled=true;post('/api/recognize/page/resume',{batch_id:batch.batch_id,source_revision:batch.source_revision,image_data:state.photoData}).then(()=>{if(state.pageBatch?.batch_id===batch.batch_id){state.batchCancelled=false;organizePage(state.photoEpoch,batch);}}).catch(error=>{if($('recognition-message'))$('recognition-message').innerHTML=notice(error.message,'error');button.disabled=false;});
 }
 if(button.id==='stop-page-work'){cancelPageWork();state.batchBusy=false;renderPageItems();}
 if(button.dataset.searchQuestion)searchQuestion(button.dataset.searchQuestion);
 if(button.dataset.openReading){button.closest('dialog')?.close();openPageReading(button.dataset.openReading);const panel=$('result')?.closest('.capture-panel');if(panel)panel.scrollTop=0;}
 if(button.dataset.retryReading){state.batchCancelled=false;const item=state.pageBatch.items.find(i=>i.reading_id===button.dataset.retryReading);if(item)organizeReading(item,state.photoEpoch,state.pageBatch);}
 if(button.dataset.retakeReading){state.photoEpoch++;resetRecognition();cancelPageWork();state.stage='select';state.showOriginal=false;syncStage();$('source-area')?.scrollIntoView({block:'start'});}
 if(button.dataset.readingChoice)selectReading(button.dataset.readingChoice);
 if(button.id==='save-card-note')saveCardNote();
 if(button.id==='confirm-ocr'){diagnoseInput();}
 if(button.id==='prev-page')selectPage(state.page-1);
 if(button.id==='next-page')selectPage(state.page+1);
 if(button.id==='crop-toggle')toggleCrop();
 if(button.id==='crop-reset')resetCrop();
 if(button.dataset.tutorPrompt)askTutor(button.dataset.tutorPrompt);
 if(button.dataset.rating)recordFeedback(button);
 if(button.id==='preview-correction')$('problem-preview').innerHTML=richHTML($('problem-source').value,true);
 if(button.dataset.hint!==undefined)toggleHint(button);
 if(button.hasAttribute('data-show-visual')){const expanded=button.getAttribute('aria-expanded')==='true';button.setAttribute('aria-expanded',String(!expanded));$('visual').classList.toggle('hidden',expanded);}
 if(button.hasAttribute('data-rearrange')){const box=button.closest('.visual-box');const packed=box.querySelector('[data-rearranged]');const original=box.querySelector('[data-before]');const open=packed.style.display!=='none';packed.style.display=open?'none':'';original.style.display=open?'':'none';button.textContent=open?'把两块拼起来 →':'再看拆开前的样子 ↶';}
 if(button.id==='start-practice')startPractice(button,{diagnosis_id:state.result?.diagnosis_id});
 if(button.dataset.review)startPractice(button,{review_id:button.dataset.review});
 if(button.hasAttribute('data-check'))checkExercise(button);
 if(button.hasAttribute('data-reload'))render();
});
document.addEventListener('input',event=>{if(event.target.id==='problem')state.problem=event.target.value;if(event.target.id==='steps')state.steps=event.target.value;});
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('[data-answer]')){event.preventDefault();event.target.closest('[data-exercise]').querySelector('[data-check]').click();}});
document.addEventListener('change',event=>{if(['camera-input','file-input'].includes(event.target.id)){const file=event.target.files[0];event.target.value='';choosePhoto(file);}if(event.target.id==='pdf-page')selectPage(Number(event.target.value));});
document.addEventListener('submit',event=>{if(event.target.id==='tutor-form'){event.preventDefault();askTutor();}});
document.addEventListener('toggle',event=>{
 const detail=event.target;if(!detail.matches?.('.line-editor')||!detail.isConnected)return;
 const input=detail.querySelector('math-field,textarea');
 if(detail.open){if(detail.dataset.original===undefined)detail.dataset.original=input?.value??'';document.querySelectorAll('.line-editor[open]').forEach(el=>{if(el!==detail)el.open=false;});}
 else if(input){const preview=document.querySelector(`[data-edit-preview="${input.id}"]`);if(preview)preview.innerHTML=input.tagName==='MATH-FIELD'?mathHTML(input.value):richHTML(input.value,true);input.blur();window.mathVirtualKeyboard?.hide();}
},true);
// A voluntary, reusable guide. Native dialog contains focus and closes with Escape.
const guide=$('usage-guide');
let guideStep=0;
const guideSteps=[['带一道题来，一起找思路。','拍下题目或上传图片、PDF。先预览，再点击识别；清晰题会整理为学习卡。'],['一点提示，让下一步清楚起来。','先找方向，再看关键一步。需要时换个例子、看看图形；看不清的原题可以重新核对。'],['练一练，把知识种进自己的树。','完成对应练习，通过三题检验解锁知识卡。写下自己的理解，放到知识树里，之后再回来复习。']];
function updateGuide(){if(!guide)return;$('guide-count').textContent=`${guideStep+1} / 3`;$('guide-title').textContent=guideSteps[guideStep][0];$('guide-body').textContent=guideSteps[guideStep][1];const art=guide.querySelector('.guide-art');art.removeAttribute('aria-hidden');art.innerHTML=`<img src="/guide-${guideStep+1}.png" alt="${['拍题预览与识别按钮示意','本题分级提示与作答区域示意','知识树与知识卡整理示意'][guideStep]}"><span>示例界面 · ${['① 上传后核对当前页，再点识别并整理','② 从一级提示开始，按需要看下一步','③ 检验达标后，在知识树整理自己的卡片'][guideStep]}</span>`;$('guide-prev').disabled=guideStep===0;$('guide-next').textContent=guideStep===2?'开始学习':'下一步';guide.querySelectorAll('.guide-dots i').forEach((el,i)=>el.classList.toggle('active',i===guideStep));}
document.addEventListener('click',event=>{if(event.target.closest('[data-open-guide]')){guideStep=0;updateGuide();guide?.showModal();}if(event.target.closest('[data-close-guide]')){rememberGuide();guide?.close();}});
const guideKey='mytree_guide_v2_'+student;
function rememberGuide(){try{localStorage.setItem(guideKey,'seen');}catch{}}
if(guide){guide.addEventListener('close',rememberGuide);$('guide-prev').onclick=()=>{guideStep=Math.max(0,guideStep-1);updateGuide();$('guide-title').focus();};$('guide-next').onclick=()=>{if(guideStep===2){rememberGuide();guide.close();$('open-camera')?.focus();return;}guideStep++;updateGuide();$('guide-title').focus();};}
window.addEventListener('popstate',render);
await render();
if(account&&guide&&location.pathname==='/'){let seen=false;try{seen=localStorage.getItem(guideKey)==='seen';}catch{}if(!seen){updateGuide();guide.showModal();}}
})();
