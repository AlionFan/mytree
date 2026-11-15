/* The child's saved cards, qualification and personally arranged tree. */
'use strict';
window.LearningUI={setup({agent,api,post,esc,richHTML,mathField,notice,app,student,navigate}){
 const $=id=>document.getElementById(id);
 const ui={cards:[],knowledge:[],today:null,quiz:null,answers:{},answerTexts:{},hints:{},unlock:null,tree:null,growth:null,selected:null,undo:null,treeMessage:'',busy:false,pending:null,lessonVersion:0};
 const pendingKey='mytree_quiz_'+student;
 try{const saved=JSON.parse(localStorage.getItem(pendingKey)||'null');if(saved&&typeof saved.requestId==='string'&&saved.params&&saved.source&&saved.answers)ui.pending=saved;}catch{}
 function savePending(){try{if(ui.pending)localStorage.setItem(pendingKey,JSON.stringify(ui.pending));}catch{}}
 const fresh=()=>crypto.randomUUID();
 const names={F:'整式与因式分解',R:'分式',N:'数与式',E:'方程',I:'不等式',U:'函数',G:'图形与几何',S:'统计',P:'概率'};
 const supported=new Set(['F1','F2','F3','F4','F5','R1','R2','R3','N1','N2','N3','N4','E1','E2','E3','E4','I1','I2','U4','P1']);
 const scoreHTML=g=>`<div class="growth-total"><strong>${g.total}</strong><span>参考成长分</span></div><dl class="growth-parts"><div><dt>规模</dt><dd>${g.components.scale}</dd></div><div><dt>茂盛度</dt><dd>${g.components.lushness}</dd></div><div><dt>关联</dt><dd>${g.components.relations}</dd></div></dl><p class="growth-note">本周 +${g.weekly_delta}</p>`;
 async function refreshHome(isCurrent=()=>true){
  try{
   const [wrong,knowledge,today,growth]=await Promise.all([agent('card.list',{type:'wrong',limit:100}),agent('card.list',{type:'knowledge',status:'active',limit:100}),agent('review.today',{}),agent('growth.get',{})]);
   if(!isCurrent())return;
   ui.cards=wrong.items;ui.knowledge=knowledge.items;ui.today=today;ui.growth=growth;
   if($('tree-preview'))$('tree-preview').innerHTML=scoreHTML(growth)+`<p class="small-text">${knowledge.items.length} 张已解锁的知识卡</p><a href="/tree" data-nav="/tree">整理我的知识树 →</a>`;
   if($('today-tasks'))$('today-tasks').innerHTML=`<div class="section-title"><div><span class="eyebrow">从一件小事开始</span><h2>今日待办</h2><button class="ghost small" data-personal-review>更新个性化复习</button><p id="personal-review-status" role="status"></p></div>${today.items.length?'<button class="ghost small" data-snooze>今天先不提醒</button>':''}</div>${today.items.length?`<div class="task-grid">${today.items.map((item,i)=>`<article class="today-task"><span class="source-tag">小任务 ${i+1}</span><p>${esc(item.reason)}</p><details><summary>安排依据 · ${item.based_on.length} 条记录</summary><p>${item.based_on.map(id=>ui.cards.find(card=>card.id===id)).filter(Boolean).map(card=>richHTML(card.problem,true)).join("；")||"已保存并核验的作答记录"}</p></details><div class="math-prose">${richHTML(item.task.prompt)}</div><button class="ghost small" data-today-task="${esc(item.id)}">开始这一项 →</button></article>`).join('')}</div>`:'<p class="empty">暂无复习任务</p>'}<div id="review-focus" aria-live="polite"></div>${ui.quiz||ui.pending?'<button class="ghost small" data-resume-quiz>继续这组三题检验 →</button>':''}`;
   if($('saved-cards'))$('saved-cards').innerHTML=`<div class="section-title"><h2>题卡</h2><span class="source-tag">最近 ${ui.cards.length} 张</span></div>${ui.cards.length?ui.cards.map(card=>`<article class="stored-wrong"><span class="source-tag">${['wrong_step','incomplete'].includes(card.study_status)?'错题卡':'学习卡'} · 已保存</span><div class="math-prose">${richHTML(card.problem,true)}</div><details><summary>一起看看，当时是怎么想的</summary>${card.student_steps.length?'<p class="teacher-note">你当时这样写：</p><ol class="learner-working">'+card.student_steps.map(step=>`<li><div class="math-prose">${richHTML(step,true)}</div></li>`).join('')+'</ol>':'<p class="teacher-note">这道题还没动笔。先说说你发现了什么？</p>'}${card.learner_note?'<p class="teacher-note">你留给自己的提醒：</p><div class="math-prose">'+richHTML(card.learner_note)+'</div>':'<p class="teacher-note">现在有新想法了吗？记下一步你想怎么做，下次一起接着想。</p>'}<label class="sr-only" for="wrong-note-${esc(card.id)}">我的新发现</label><textarea class="wrong-note-input" id="wrong-note-${esc(card.id)}" maxlength="3000" placeholder="我发现…… / 我下一步想……">${esc(card.learner_note||'')}</textarea><button class="ghost small" data-save-wrong-note="${esc(card.id)}">记下这个想法</button><div data-wrong-note-status aria-live="polite"></div></details>${cardActions(card)}</article>`).join(''):'<p class="empty">暂无题卡</p>'}`;
  }catch(error){if(!isCurrent())return;for(const id of ['today-tasks','tree-preview','saved-cards'])if($(id))$(id).innerHTML=notice(error.message+' 可以重新读取。','error')+'<button class="ghost" data-home-retry>重新读取</button>';}
 }
 function cardActions(card){const actions=card.knowledge_ids.filter(key=>supported.has(key)).map(key=>`<button class="ghost small" data-quiz-card="${esc(card.id)}" data-quiz-knowledge="${esc(key)}">做三题检验${card.knowledge_ids.length>1?' · '+esc(names[key[0]]||'对应方法'):''}</button>`).join('');return `<div class="row quiz-actions">${actions}<button class="ghost small" data-diagram-lesson="${esc(card.diagnosis_id)}">解题思路与步骤</button></div>`;}
 function dialog(){let element=$('quiz-dialog');if(!element){element=document.createElement('dialog');element.id='quiz-dialog';element.className='quiz-dialog';element.setAttribute('aria-labelledby','quiz-heading');document.body.append(element);}return element;}
 async function startQuiz(cardId,knowledge,reviewId){
  ui.lessonVersion++;
  const box=dialog();box.innerHTML='<p role="status">正在准备服务端核验的三题检验…</p>';if(!box.open)box.showModal();
  let card=ui.cards.find(item=>item.id===cardId);
  try{
   if(!card){ui.cards=(await agent('card.list',{type:'wrong',limit:100})).items;card=ui.cards.find(item=>item.id===cardId);}
   if(!card)throw new Error('来源题目卡没有找到，请重新读取。');
   const params={knowledge_id:knowledge,source_wrong_card_ids:[cardId],...(reviewId?{review_id:reviewId}:{})},requestId=fresh();
   const group=await agent('quiz.start',params,requestId);
   ui.pending={params,requestId,source:card,answers:{}};savePending();
   ui.quiz={...group,source:card,reviewId};ui.answers={};ui.answerTexts={};ui.hints={};ui.unlock=null;renderQuiz();
  }catch(error){box.innerHTML=`<h2 id="quiz-heading">这组检验还没准备好</h2>${notice(error.message,'error')}${card?`<button data-quiz-lesson data-lesson-card="${esc(card.id)}" data-lesson-knowledge="${esc(knowledge)}">回到知识讲解</button>`:''}<button class="ghost" data-close-quiz>回到学习桌</button>`;}
 }
 async function resumeQuiz(){
  if(ui.quiz){renderQuiz();return;}
  const saved=ui.pending;if(!saved)return;
  const box=dialog();box.innerHTML='<p role="status">正在从服务端恢复这组检验…</p>';if(!box.open)box.showModal();
  try{
   const group=await agent('quiz.start',saved.params,saved.requestId);
   ui.quiz={...group,source:saved.source,reviewId:saved.params.review_id};ui.answers={};ui.answerTexts={};ui.hints={};ui.unlock=null;
   for(const item of group.items){const answer=saved.answers[item.id];if(typeof answer==='string'&&answer){ui.answerTexts[item.id]=answer;ui.answers[item.id]=await agent('quiz.answer',{quiz_id:group.quiz_id,exercise_id:item.id,answer});}}
   if(Object.values(ui.answers).some(answer=>answer.progress.complete))ui.unlock=await agent('card.unlock',{quiz_id:group.quiz_id});
   renderQuiz();
  }catch(error){box.innerHTML=`<h2 id="quiz-heading">检验暂时没有恢复</h2>${notice(error.message,'error')}<button data-close-quiz>返回，稍后重试</button>`;}
 }
 function renderQuiz(){
  ui.lessonVersion++;
  const q=ui.quiz;if(!q)return;const box=dialog();
  box.innerHTML=`<div class="section-title"><div><h2 id="quiz-heading">检验</h2></div><button class="ghost small" data-close-quiz aria-label="暂时退出检验">暂时退出</button></div><div class="quiz-items">${q.items.map((item,index)=>`<section class="quiz-item" data-quiz-item="${esc(item.id)}"><span class="source-tag">第 ${index+1} 题${item.is_transfer?' · 迁移题':''}</span><div class="math-prose">${richHTML(item.prompt)}</div><form data-quiz-answer="${esc(item.id)}"><label for="quiz-answer-${index}">我的答案</label><div class="row answer-row">${item.answer_kind==='choice'?`<select id="quiz-answer-${index}" aria-label="第 ${index+1} 题检验答案" ${ui.answers[item.id]?'disabled':''}><option value="">选择选项</option>${['A','B','C','D'].map(label=>`<option value="${label}" ${ui.answerTexts[item.id]===label?'selected':''}>${label}</option>`).join('')}</select>`:mathField(ui.answerTexts[item.id]||'',`id="quiz-answer-${index}" aria-label="第 ${index+1} 题检验答案" ${ui.answers[item.id]?'read-only':''}`)}<button type="submit" ${ui.answers[item.id]?'disabled':''}>${ui.answers[item.id]?'已保存':'提交这一题'}</button></div></form><div class="row hint-actions">${[1,2,3].map(level=>`<button class="ghost small" data-quiz-hint="${level}" data-exercise-id="${esc(item.id)}" ${level>1&&!ui.hints[item.id]?.[level-1]?'disabled':''}>${['找方向','想关键一步','看完整解法'][level-1]}</button>`).join('')}</div><div data-quiz-hint-text class="math-prose" aria-live="polite"></div><div data-quiz-feedback aria-live="polite">${ui.answers[item.id]?notice(ui.answers[item.id].correct?'这题已通过，答题事实已保存。':'这题还需再看看，本次作答已保留。'):''}</div></section>`).join('')}</div><div id="quiz-summary" aria-live="polite"></div>`;
  showQuizSummary();if(!box.open)box.showModal();
 }
 async function submitQuiz(form){
  const id=form.dataset.quizAnswer,input=form.querySelector('math-field,select'),button=form.querySelector('button'),section=form.closest('[data-quiz-item]');
  if(!input.value.trim()){section.querySelector('[data-quiz-feedback]').innerHTML=notice('先写下你的答案。');input.focus();return;}
  button.disabled=true;
  ui.answerTexts[id]=input.value.trim();if(ui.pending){ui.pending.answers[id]=input.value.trim();savePending();}
  try{const result=await agent('quiz.answer',{quiz_id:ui.quiz.quiz_id,exercise_id:id,answer:input.value.trim()});ui.answers[id]=result;input.readOnly=true;if(input.tagName==='SELECT')input.disabled=true;button.textContent='已保存';section.querySelector('[data-quiz-feedback]').innerHTML=notice(result.correct?'这题已通过，答题事实已保存。':'这题还需再看看，本次作答已保留。');
   if(result.progress.complete){ui.unlock=await agent('card.unlock',{quiz_id:ui.quiz.quiz_id});if(ui.quiz.reviewId)await agent('review.complete',{review_id:ui.quiz.reviewId,evidence_ids:Object.values(ui.answers).map(item=>item.evidence_id)});showQuizSummary();await post('/api/review/personalize',{});refreshHome();}
  }catch(error){section.querySelector('[data-quiz-feedback]').innerHTML=notice(error.message+' 可以再次提交。','error');button.disabled=false;}
 }
 async function loadLesson(card,knowledge){
  const query=new URLSearchParams({student,source_wrong_card_id:card.id,knowledge_id:knowledge});
  return api('/api/quiz/lesson?'+query);
 }
 async function showLesson(card,knowledge){
  const version=++ui.lessonVersion;
  const box=dialog();box.innerHTML='<h2 id="quiz-heading">正在读取知识讲解…</h2><p role="status">只回顾已有规则和原作答，不会新建题目或卡片。</p>';if(!box.open)box.showModal();
  try{const lesson=await loadLesson(card,knowledge);if(!box.isConnected||version!==ui.lessonVersion||!box.open)return;
   box.innerHTML=`<section class="knowledge-lesson"><span class="source-tag">回到规则，慢慢想</span><h2 id="quiz-heading">${esc(lesson.title)}</h2>${lesson.paused?notice('这个知识点今天先不出新检验，'+lesson.resume_on+'（北京时间）起恢复。其他知识点照常。'):''}<div class="knowledge-card"><div class="math-prose">${richHTML(lesson.rule,true)}</div><p class="math-prose">${richHTML(lesson.tip,true)}</p></div><h3>回看当时这道题</h3><div class="math-prose">${richHTML(lesson.problem,true)}</div>${lesson.student_steps.map((line,i)=>`<div class="math-prose"><span class="source-tag">原作答第 ${i+1} 行</span>${richHTML(line,true)}</div>`).join('')}<p class="field-tip">${esc(lesson.verification.label)}。可以先遮住作答，说说这一步用了什么规则。</p><div class="row"><button data-close-quiz>回到学习桌</button>${ui.quiz?.source.id===card.id?'<button class="ghost" data-resume-quiz>回看这组作答</button>':''}${!lesson.paused?`<button class="ghost" data-quiz-card="${esc(card.id)}" data-quiz-knowledge="${esc(knowledge)}">重新开始检验</button>`:''}</div></section>`;
  }catch(error){if(version!==ui.lessonVersion||!box.open)return;box.innerHTML=`<h2 id="quiz-heading">知识讲解暂时没有读到</h2>${notice(error.message,'error')}<button data-quiz-lesson data-lesson-card="${esc(card.id)}" data-lesson-knowledge="${esc(knowledge)}">重新读取讲解</button><button class="ghost" data-close-quiz>回到学习桌</button>`;}
 }
 async function showQuizSummary(){
  const box=$('quiz-summary');if(!box||!ui.unlock)return;const unlocked=ui.unlock,q=ui.quiz,completed=Object.values(ui.answers).find(item=>item.progress.complete),stopped=completed?.next_step==='stop_and_explain';
  let paused=false,resumeOn=null;
  if(stopped){
   box.innerHTML='<p role="status">正在核对这个知识点今天的检验安排…</p>';
   try{const lesson=await loadLesson(q.source,q.knowledge_id);if(!box.isConnected||q.quiz_id!==ui.quiz?.quiz_id)return;paused=lesson.paused;resumeOn=lesson.resume_on;}
   catch(error){if(box.isConnected)box.innerHTML=`<section><h2>学习状态暂时没有读到</h2>${notice(error.message,'error')}<button data-retry-quiz-state>重新读取学习状态</button><button class="ghost" data-close-quiz>回到学习桌</button></section>`;return;}
  }
  if(!box.isConnected||q.quiz_id!==ui.quiz?.quiz_id)return;
  const next=paused?`<p class="field-tip">这个知识点的新检验 ${esc(resumeOn)}（北京时间）起恢复，其他知识点照常。</p><button data-quiz-lesson data-lesson-card="${esc(q.source.id)}" data-lesson-knowledge="${esc(q.knowledge_id)}">先回到知识讲解 →</button>`:'<button class="ghost" data-new-quiz>准备好后，再试一组</button>';
  box.innerHTML=`<section class="unlock-result ${unlocked.unlocked?'unlocked':''}"><h2>${unlocked.unlocked?'已通过，知识卡解锁了。':paused?'今天先回到讲解，慢慢想。':'还差一点，先回顾再来。'}</h2>${unlocked.unlocked?'':unlocked.reasons.map(reason=>notice(reason)).join('')}${unlocked.unlocked?`<article class="knowledge-card"><span class="source-tag">${unlocked.reused_existing?'已有的知识卡 · 本次记录保留':'新知识卡'}</span><h3>${esc(unlocked.card.title)}</h3><div class="math-prose">${richHTML(unlocked.card.rule,true)}</div><label for="unlocked-note">用自己的话记一句</label><textarea id="unlocked-note" maxlength="3000">${esc(unlocked.card.learner_note||'')}</textarea><button class="ghost small" data-save-unlocked-note>保存笔记</button><div id="unlocked-note-status" aria-live="polite"></div><button data-visit-tree>整理到我的知识树 →</button></article>`:''}<p class="field-tip">${esc(stopped&&!paused?'今天可以重新开始这个知识点的检验。':completed?.reason||'')}</p>${unlocked.unlocked?'':next}</section>`;
 }
 async function quizHint(button){
  const id=button.dataset.exerciseId,level=Number(button.dataset.quizHint),section=button.closest('[data-quiz-item]'),out=section.querySelector('[data-quiz-hint-text]');button.disabled=true;
  try{const value=await post('/api/hint',{diagnosis_id:ui.quiz.source.diagnosis_id,quiz_id:ui.quiz.quiz_id,exercise_id:id,level});(ui.hints[id]??={})[level]=value.text;out.innerHTML=richHTML(value.text,true);const next=section.querySelector(`[data-quiz-hint="${level+1}"]`);if(next)next.disabled=false;}
  catch(error){out.innerHTML=notice(error.message,'error');}finally{button.disabled=false;}
 }
 async function saveWrongNote(button){const id=button.dataset.saveWrongNote,card=ui.cards.find(c=>c.id===id),box=button.closest('.stored-wrong'),out=box.querySelector('[data-wrong-note-status]');if(!card)return;button.disabled=true;try{const result=await post('/api/cards/edit',{card_id:id,expected_revision:card.revision,learner_note:box.querySelector('.wrong-note-input').value,request_id:fresh()});ui.cards=ui.cards.map(c=>c.id===id?result.card:c);out.innerHTML=notice('已记下，下次一起接着想。','success');}catch(e){out.innerHTML=notice(e.message,'error');}finally{button.disabled=false;}}
 async function openTask(id){
  const item=ui.today?.items.find(task=>task.id===id);if(!item)return;
  const card=ui.cards.find(card=>item.based_on.includes(card.id)&&card.knowledge_ids.includes(item.knowledge_id));
  $('review-focus').innerHTML=`<section class="review-focus"><h3>先回忆，再验证</h3><div class="math-prose">${richHTML(item.task.prompt)}</div><p class="field-tip">可以先遮住解法，用自己的话说一说，再尝试检验。</p>${card&&supported.has(item.knowledge_id)?`<button data-quiz-card="${esc(card.id)}" data-quiz-knowledge="${esc(item.knowledge_id)}" data-review-id="${esc(item.id)}">从三题检验开始 →</button>`:'<p>这个知识点的程序检验还没准备好，可以先回看题目卡。</p>'}</section>`;
 }
 async function renderTree(isCurrent=()=>true){
  app.innerHTML=`<div class="page-intro"><h1>知识树</h1></div><div id="tree-content" role="status">正在读取知识卡与参考目录…</div>`;
  try{
   const [tree,cards,growth]=await Promise.all([agent('tree.get',{}),agent('card.list',{type:'knowledge',limit:100}),agent('growth.get',{})]);if(!isCurrent())return;ui.tree=tree;ui.knowledge=cards.items;ui.growth=growth;
   const active=cards.items.filter(card=>card.status==='active');if(!active.some(card=>card.id===ui.selected))ui.selected=active[0]?.id||null;
   const placed=new Map(tree.placements.map(item=>[item.card_id,item]));
   $('tree-content').innerHTML=`<div class="tree-workspace"><section><div class="panel tree-toolbar"><div class="section-title"><h2>知识树</h2><span class="tree-card-count">${active.length} 张知识卡</span></div><div class="tree-actions">${ui.undo?'<button class="ghost small" data-tree-undo aria-label="撤销上次整理">撤销</button>':''}<button data-learn-selected ${ui.selected?'':'disabled'}>学习</button><button class="ghost" data-edit-selected ${ui.selected?'':'disabled'}>整理</button><button class="ghost" data-tree-directory>目录</button></div><div id="tree-action-status" aria-live="polite">${ui.treeMessage?notice(ui.treeMessage):''}</div><div class="unplaced-cards">${active.filter(card=>!placed.has(card.id)).map(card=>`<button class="ghost small" data-select-card="${esc(card.id)}">＋ ${esc(card.title)}</button>`).join('')}${!active.length?'<p class="empty">还没有知识卡</p><a href="/" data-nav="/">去拍一道题</a>':''}</div><div id="tree-canvas" class="tree-canvas" aria-label="自由整理知识卡的画布"><svg class="tree-silhouette" viewBox="0 0 900 640" aria-hidden="true"><defs><linearGradient id="tree-wood" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#4d7b5d"/><stop offset="1" stop-color="#9db889"/></linearGradient><linearGradient id="tree-foliage"><stop stop-color="#c3dd9d"/><stop offset="1" stop-color="#7fac80"/></linearGradient></defs><path d="M450 607V283m0 211C333 494 215 425 165 319m285 112c112 0 238-63 285-168M450 355c-74 0-135-48-158-122m158 81c61 0 123-54 139-129" fill="none" stroke="url(#tree-wood)" stroke-width="13" stroke-linecap="round"/><path d="M162 325c-96-15-125-82-111-145 84 1 138 49 111 145Zm130-87c-77-6-112-58-104-123 68 0 122 47 104 123Zm299-49c-3-89 51-137 123-134 5 73-43 133-123 134Zm143 81c11-87 74-123 145-105-13 77-62 117-145 105Z" fill="url(#tree-foliage)"/><ellipse cx="450" cy="610" rx="116" ry="7" fill="currentColor"/></svg><svg class="tree-links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${tree.links.map(link=>{const a=placed.get(link.from),b=placed.get(link.to);return a&&b?`<path d="M${clamp(a.position.x)} ${clamp(a.position.y)} L${clamp(b.position.x)} ${clamp(b.position.y)}"/>`:'';}).join('')}</svg>${active.filter(card=>placed.has(card.id)).map(card=>{const p=placed.get(card.id).position,x=clamp(p.x),y=clamp(p.y);return `<button class="tree-leaf ${card.id===ui.selected?'selected':''}" style="left:${x}%;top:${y}%;transform:translate(-${x}%,-${y}%)" data-tree-card="${esc(card.id)}" aria-label="${esc(card.title)}，用箭头键移动" aria-pressed="${card.id===ui.selected}"><span class="source-tag">${esc(card.knowledge_id)}</span><strong>${esc(card.title)}</strong></button>`;}).join('')}</div><dialog class="tree-editor-dialog" id="tree-editor-dialog" aria-label="整理知识卡"><div class="section-title"><h2>整理</h2><button class="ghost small" data-close-tree-editor>关闭</button></div><div id="tree-editor"></div></dialog></div><dialog class="reference-tree" id="tree-directory"><div class="section-title"><h2>知识目录</h2><button class="ghost small" data-close-directory>关闭</button></div><p class="field-tip">这是初中数学参考目录，未绑定具体教材版本。你可以自由编排；连线只对照已列出的前置关系。</p><div class="reference-grid">${tree.skeleton.map(item=>`<div><strong>${esc(item.name)}</strong><small>${esc(item.id)}${item.pre?' ← '+esc(item.pre):' · 起点'}</small></div>`).join('')}</div></dialog></section><aside class="panel tree-growth"><h2>成长</h2>${scoreHTML(growth)}${cards.items.some(card=>card.status==='removed')?`<details><summary>收起的知识卡</summary>${cards.items.filter(card=>card.status==='removed').map(card=>`<button class="ghost small" data-restore-card="${esc(card.id)}">放回 ${esc(card.title)}</button>`).join('')}</details>`:''}</aside></div>`;
   const canvas=$('tree-canvas');
   if(tree.links.length){
    const namesById=new Map(cards.items.map(card=>[card.id,card.title]));
    canvas.insertAdjacentHTML('afterend',`<section class="tree-relation-list"><h3>我保留的联系</h3>${tree.links.map(link=>`<article><strong>${esc(namesById.get(link.from)||'知识卡')} → ${esc(namesById.get(link.to)||'知识卡')}</strong><div class="math-prose">${richHTML(link.relation_reason||'')}</div></article>`).join('')}</section>`);
   }
   renderEditor();installDrag();
  }catch(error){if(isCurrent())$('tree-content').innerHTML=notice(error.message+' 请重新读取。','error')+'<button class="ghost" data-tree-retry>重新读取</button>';}
 }
 const clamp=x=>Math.max(0,Math.min(100,Number(x)||0));
 function renderEditor(){
  const card=ui.knowledge.find(card=>card.id===ui.selected),box=$('tree-editor');if(!box)return;if(!card){box.innerHTML='';return;}
  const p=ui.tree.placements.find(item=>item.card_id===card.id)||{parent_id:null,position:{x:30,y:30}};
  box.innerHTML=`<section class="tree-editor"><h3>${esc(card.title)}</h3><div class="editor-tabs"><button class="ghost small" data-editor-tab="position">位置</button><button class="ghost small" data-editor-tab="links">连线</button><button class="ghost small" data-editor-tab="note">笔记</button></div><div data-editor-pane="position"><form id="tree-position"><label for="tree-parent">放入哪里</label><select id="tree-parent"><option value="">树的空白处</option><optgroup label="我建的分组">${ui.tree.groups.map(g=>`<option value="${esc(g.id)}" ${p.parent_id===g.id?'selected':''}>${esc(g.title)}</option>`).join('')}</optgroup><optgroup label="参考目录">${ui.tree.skeleton.map(k=>`<option value="${esc(k.id)}" ${p.parent_id===k.id?'selected':''}>${esc(k.name)}</option>`).join('')}</optgroup></select><div class="position-fields"><label>横向位置（0–100）<input id="tree-x" type="number" min="0" max="100" step="1" value="${clamp(p.position.x)}" required></label><label>纵向位置（0–100）<input id="tree-y" type="number" min="0" max="100" step="1" value="${clamp(p.position.y)}" required></label></div><button type="submit">保存位置</button></form><div class="row"><label for="tree-group">新建或放入分组<input id="tree-group" maxlength="200" placeholder="例如：我常用的公式"></label><button class="ghost small" data-tree-group>放入这个分组</button></div></div><div class="tree-connect" data-editor-pane="links" hidden><h3>连线</h3><label for="tree-target">这张卡指向</label><select id="tree-target"><option value="">选择另一张卡</option>${ui.knowledge.filter(other=>other.id!==card.id&&other.status==='active').map(other=>`<option value="${esc(other.id)}">${esc(other.title)}</option>`).join('')}</select><label for="tree-reason">我为什么这样连</label><textarea id="tree-reason" maxlength="1000" placeholder="用自己的话写一句"></textarea><button class="ghost small" data-tree-link>保留这条联系</button></div><div data-editor-pane="note" hidden><label for="tree-note">笔记</label><textarea id="tree-note" maxlength="3000">${esc(card.learner_note||'')}</textarea><div class="row"><button class="ghost small" data-tree-save-note>保存笔记</button><button class="ghost small" data-remove-card>收起</button></div></div></section>`;
 }
 async function mutate(params,method='menu'){
  if(ui.busy)return;ui.busy=true;
  try{const value=await agent('tree.move',{...params,method,expected_revision:ui.tree.revision});ui.undo=params.action==='undo'?null:value.undo;
   ui.treeMessage=value.relation_assessment?.reason||(params.action==='undo'?'已撤销最近一次整理，历史成长分保留。':'整理已保存，刷新后还在。');await renderTree();
   if(method==='keyboard')document.querySelector(`[data-tree-card="${CSS.escape(ui.selected||'')}"]`)?.focus({preventScroll:true});
  }catch(error){ui.undo=null;ui.treeMessage=error.message+' 已重新读取，请核对后重试。';await renderTree();}finally{ui.busy=false;}
 }
 async function editKnowledge(card,changes,out){try{await agent('card.edit',{card_id:card.id,expected_revision:card.revision,...changes});ui.treeMessage='知识卡修改已保存。';if(out){out.innerHTML=notice('笔记已保存。','success');return;}await renderTree();}catch(error){if(out)out.innerHTML=notice(error.message,'error');else{ui.treeMessage=error.message;await renderTree();}}}

 function knowledgeDialog(){let box=$('knowledge-lesson');if(!box){box=document.createElement('dialog');box.id='knowledge-lesson';box.className='knowledge-lesson-dialog';box.setAttribute('aria-labelledby','knowledge-heading');document.body.append(box);}return box;}
 async function openKnowledge(id){const card=ui.knowledge.find(c=>c.id===id&&c.status==='active');if(!card)return;ui.knowledgeLesson={card,variant:0,data:null,solution:null,step:0,answer:'',feedback:''};const box=knowledgeDialog();box.innerHTML='<h2 id="knowledge-heading">例题</h2><p role="status">读取中…</p><button class="ghost" data-close-knowledge>关闭</button>';if(!box.open)box.showModal();await loadKnowledge('open',0);}
 function beginKnowledgeRequest(current,label){
  const box=knowledgeDialog();if(!current||current.busy||!box.open)return null;
  current.answer=$('knowledge-answer')?.value??current.answer;current.busy=true;
  const token={current,cardId:current.card.id,variant:current.variant,sequence:(current.sequence||0)+1};current.sequence=token.sequence;
  box.querySelectorAll('button:not([data-close-knowledge])').forEach(b=>b.disabled=true);
  const answer=$('knowledge-answer');if(answer){answer.readOnly=true;if(answer.tagName==='SELECT')answer.disabled=true;}
  const status=box.querySelector('.knowledge-feedback');if(status)status.textContent=label;
  return token;
 }
 function currentKnowledgeRequest(token){const box=$('knowledge-lesson');return token&&ui.knowledgeLesson===token.current&&box?.open&&token.current.card.id===token.cardId&&token.current.variant===token.variant&&token.current.sequence===token.sequence;}
 async function loadKnowledge(action,variant){
  const current=ui.knowledgeLesson,token=beginKnowledgeRequest(current,'读取中…');if(!token)return;
  try{const data=await post('/api/knowledge/learn',{action,card_id:token.cardId,variant});if(!currentKnowledgeRequest(token))return;Object.assign(current,{data,variant,solution:null,hint:null,step:0,answer:'',feedback:'',busy:false});renderKnowledge();}
  catch(e){if(!currentKnowledgeRequest(token))return;current.feedback=e.message;current.busy=false;renderKnowledge();}
 }
 function renderKnowledge(){const current=ui.knowledgeLesson;if(!current)return;const {card,data,variant}=current;const box=knowledgeDialog();box.innerHTML=`<div class="section-title"><div><span class="source-tag">${variant?'同类练习 '+variant:'经典例题'}</span><h2 id="knowledge-heading">${esc(data?.title||card.title)}</h2></div><button class="ghost small" data-close-knowledge>关闭</button></div>${data?`<div class="knowledge-question math-prose">${richHTML(data.prompt)}</div><form id="knowledge-answer-form"><label for="knowledge-answer">答案</label><div class="row answer-row">${data.answer_kind==='choice'?`<select id="knowledge-answer" aria-label="例题答案"><option value="">选择选项</option>${['A','B','C','D'].map(label=>`<option value="${label}" ${current.answer===label?'selected':''}>${label}</option>`).join('')}</select>`:mathField(current.answer,'id="knowledge-answer" aria-label="例题答案"')}<button type="submit">检查</button></div></form><div class="knowledge-feedback" role="status">${current.feedback?notice(current.feedback):''}</div><div class="knowledge-explanation math-prose">${current.solution?richHTML(current.solution.steps[current.step]):current.hint?richHTML(current.hint):''}</div>${current.solution?`<div class="lesson-steps"><button class="ghost small" data-example-step="-1" ${current.step===0?'disabled':''}>上一步</button><span>${current.step+1} / ${current.solution.steps.length}</span><button class="ghost small" data-example-step="1" ${current.step===current.solution.steps.length-1?'disabled':''}>下一步</button></div>`:''}<div class="knowledge-actions"><button class="ghost" data-example-hint>提示</button><button class="ghost" data-example-solution>解法</button><button data-example-next ${variant>=50?'disabled':''}>再练一题</button></div>`:notice(current.feedback||'读取失败，请重试。','error')+'<button data-example-retry>重试</button>'}`;}
 async function knowledgeAction(action){
  const current=ui.knowledgeLesson,token=beginKnowledgeRequest(current,'核对中…');if(!token)return;
  try{const result=await post('/api/knowledge/learn',{action,card_id:token.cardId,variant:token.variant,...(action==='answer'?{answer:current.answer}:{})});if(!currentKnowledgeRequest(token))return;if(action==='hint'){current.hint=result.hint;current.solution=null;}if(action==='solution'){current.solution=result;current.step=0;}if(action==='answer')current.feedback=result.feedback;current.busy=false;renderKnowledge();}
  catch(e){if(!currentKnowledgeRequest(token))return;current.feedback=e.message;current.busy=false;renderKnowledge();}
 }
 function selectCard(id){ui.selected=id;document.querySelectorAll('[data-tree-card]').forEach(node=>{node.classList.toggle('selected',node.dataset.treeCard===id);node.setAttribute('aria-pressed',String(node.dataset.treeCard===id));});renderEditor();}
 function installDrag(){
  const board=$('tree-canvas');if(!board)return;let drag=null;
  board.addEventListener('pointerdown',event=>{const node=event.target.closest('[data-tree-card]');if(!node||event.button!==0)return;selectCard(node.dataset.treeCard);drag={node,id:node.dataset.treeCard,startX:event.clientX,startY:event.clientY,moved:false};node.setPointerCapture(event.pointerId);});
  board.addEventListener('pointermove',event=>{if(!drag)return;if(Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)<6&&!drag.moved)return;drag.moved=true;const rect=board.getBoundingClientRect(),leaf=drag.node.getBoundingClientRect();drag.x=clamp((event.clientX-rect.left-leaf.width/2)/(rect.width-leaf.width)*100);drag.y=clamp((event.clientY-rect.top-leaf.height/2)/(rect.height-leaf.height)*100);drag.node.style.left=drag.x+'%';drag.node.style.top=drag.y+'%';drag.node.style.transform=`translate(-${drag.x}%,-${drag.y}%)`;});
  board.addEventListener('pointerup',()=>{if(!drag)return;const done=drag;drag=null;if(done.moved){ui.justDragged=true;setTimeout(()=>{ui.justDragged=false;},0);const old=ui.tree.placements.find(p=>p.card_id===done.id);mutate({action:'move',card_id:done.id,parent_id:old?.parent_id||null,position:{x:Math.round(done.x),y:Math.round(done.y)}},'drag');}});
  board.addEventListener('pointercancel',()=>{if(drag){drag=null;renderTree();}});
 }
 document.addEventListener('click',async event=>{
  const b=event.target.closest('button');if(!b||b.disabled)return;
  if(b.dataset.saveWrongNote)saveWrongNote(b);
  if(b.hasAttribute('data-close-knowledge')){knowledgeDialog().close();ui.knowledgeLesson=null;}
  if(b.hasAttribute('data-example-hint'))knowledgeAction('hint');
  if(b.hasAttribute('data-example-solution'))knowledgeAction('solution');
  if(b.hasAttribute('data-example-next')){if(ui.knowledgeLesson&&!ui.knowledgeLesson.busy)await loadKnowledge('next',ui.knowledgeLesson.variant+1);}
  if(b.hasAttribute('data-example-retry'))loadKnowledge('open',0);
  if(b.dataset.exampleStep&&ui.knowledgeLesson&&!ui.knowledgeLesson.busy){ui.knowledgeLesson.answer=$('knowledge-answer')?.value||'';ui.knowledgeLesson.step+=Number(b.dataset.exampleStep);renderKnowledge();}
  if(b.dataset.quizCard)startQuiz(b.dataset.quizCard,b.dataset.quizKnowledge,b.dataset.reviewId);
  if(b.hasAttribute('data-close-quiz')){ui.lessonVersion++;dialog().close();}
  if(b.hasAttribute('data-resume-quiz'))resumeQuiz();
  if(b.hasAttribute('data-new-quiz'))startQuiz(ui.quiz.source.id,ui.quiz.knowledge_id,ui.quiz.reviewId);
  if(b.hasAttribute('data-retry-quiz-state'))showQuizSummary();
  if(b.hasAttribute('data-quiz-lesson')){const card=ui.cards.find(item=>item.id===b.dataset.lessonCard)||ui.quiz?.source||ui.pending?.source;if(card)showLesson(card,b.dataset.lessonKnowledge);}
  if(b.dataset.quizHint)quizHint(b);
  if(b.dataset.todayTask)openTask(b.dataset.todayTask);
  if(b.hasAttribute('data-personal-review')){b.disabled=true;const out=$('personal-review-status');out.textContent='正在读取以往作答和复习记忆…';try{const result=await post('/api/review/personalize',{},90000);await refreshHome();$('personal-review-status').textContent=(result.memory.engine==='mem0'?'长期学习记忆已更新。':'')+result.message;}catch(error){out.textContent=error.message;b.disabled=false;}}
  if(b.hasAttribute('data-home-retry'))refreshHome();
  if(b.hasAttribute('data-snooze')){b.disabled=true;try{await post('/api/review/snooze',{reminder_key:ui.today.reminder_key});await refreshHome();if($('review-focus'))$('review-focus').innerHTML=notice('今天不再提醒，任务仍留在这里。');}catch(error){b.disabled=false;$('review-focus').innerHTML=notice(error.message,'error');}}
  if(b.hasAttribute('data-save-unlocked-note')){b.disabled=true;try{const result=await agent('card.edit',{card_id:ui.unlock.card.id,expected_revision:ui.unlock.card.revision,learner_note:$('unlocked-note').value});ui.unlock.card=result.card;$('unlocked-note-status').innerHTML=notice('笔记已保存。','success');}catch(error){$('unlocked-note-status').innerHTML=notice(error.message,'error');}finally{b.disabled=false;}}
  if(b.hasAttribute('data-visit-tree')){dialog().close();navigate('/tree');}
  if(b.dataset.selectCard||b.dataset.treeCard){selectCard(b.dataset.selectCard||b.dataset.treeCard);if(!ui.justDragged)openKnowledge(ui.selected);ui.justDragged=false;}
  if(b.hasAttribute('data-learn-selected'))openKnowledge(ui.selected);
  if(b.hasAttribute('data-edit-selected')){renderEditor();$('tree-editor-dialog')?.showModal();}
  if(b.hasAttribute('data-close-tree-editor'))$('tree-editor-dialog')?.close();
  if(b.hasAttribute('data-tree-directory'))$('tree-directory')?.showModal();
  if(b.hasAttribute('data-close-directory'))$('tree-directory')?.close();
  if(b.dataset.editorTab){document.querySelectorAll('[data-editor-pane]').forEach(el=>{el.hidden=el.dataset.editorPane!==b.dataset.editorTab;});}
  if(b.hasAttribute('data-tree-retry'))renderTree();
  if(b.hasAttribute('data-tree-undo')&&ui.undo)mutate({action:'undo',undo_token:ui.undo.token});
  if(b.hasAttribute('data-tree-group'))mutate({action:'group',card_id:ui.selected,group_title:$('tree-group').value});
  if(b.hasAttribute('data-tree-link'))mutate({action:'link',card_id:ui.selected,target_card_id:$('tree-target').value,relation_reason:$('tree-reason').value});
  const card=ui.knowledge.find(card=>card.id===ui.selected);
  if(b.hasAttribute('data-tree-save-note')&&card)editKnowledge(card,{learner_note:$('tree-note').value});
  if(b.hasAttribute('data-remove-card')&&card){ui.undo=null;editKnowledge(card,{status:'removed'});}
  if(b.dataset.restoreCard){const restore=ui.knowledge.find(card=>card.id===b.dataset.restoreCard);if(restore)editKnowledge(restore,{status:'active'});}
 });
 document.addEventListener('submit',event=>{
  if(event.target.id==='knowledge-answer-form'){event.preventDefault();knowledgeAction('answer');}
  if(event.target.matches('[data-quiz-answer]')){event.preventDefault();submitQuiz(event.target);}
  if(event.target.id==='tree-position'){event.preventDefault();mutate({action:'move',card_id:ui.selected,parent_id:$('tree-parent').value||null,position:{x:Number($('tree-x').value),y:Number($('tree-y').value)}},'menu');}
 });
 document.addEventListener('keydown',event=>{
  const card=event.target.closest('[data-tree-card]');if(!card||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();ui.selected=card.dataset.treeCard;
  const old=ui.tree.placements.find(item=>item.card_id===ui.selected);if(!old)return;const p={...old.position};p.x=clamp(p.x+(event.key==='ArrowRight'?5:event.key==='ArrowLeft'?-5:0));p.y=clamp(p.y+(event.key==='ArrowDown'?5:event.key==='ArrowUp'?-5:0));mutate({action:'move',card_id:ui.selected,parent_id:old.parent_id,position:p},'keyboard');
 });
 return {refreshHome,renderTree,cardActions};
}};
