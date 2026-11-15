/* Requires an isolated fake-upstream service with a test-only answer oracle.
   Never point this script at a real classroom profile or a paid model service. */
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import readline from 'node:readline';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.MYTREE_PLAYWRIGHT_PATH||'/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const service=spawn(path.resolve(import.meta.dirname,'../.venv/bin/python'),[path.join(import.meta.dirname,'serve_qa_phase_b.py')],{stdio:['ignore','pipe','pipe']});
const config=await new Promise((resolve,reject)=>{const lines=readline.createInterface({input:service.stdout});const timer=setTimeout(()=>reject(new Error('QA service did not start')),15000);lines.once('line',line=>{clearTimeout(timer);try{resolve(JSON.parse(line));}catch(error){reject(error);}});service.once('error',reject);service.once('exit',code=>{clearTimeout(timer);reject(new Error('QA service exited '+code));});});
if(!config.profile.startsWith('/var/folders/')&&!config.profile.startsWith('/tmp/'))throw new Error('QA service must use a temporary profile');
const outputIndex=process.argv.indexOf('--output');
const out=outputIndex>=0?path.resolve(process.argv[outputIndex+1]):path.resolve(import.meta.dirname,'../../docs/evidence/phase-b-ui');fs.mkdirSync(out,{recursive:true});
const report={mode:'synthetic-photo-fake-upstream-real-business-http',errors:[],checks:[],viewports:[],mutations:[]};
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
let group=null;
page.on('pageerror',error=>report.errors.push(error.message));
page.on('response',async response=>{try{const request=response.request();if(new URL(response.url()).pathname!=='/api/agent'||request.method()!=='POST')return;const body=request.postDataJSON(),result=await response.json();if(body.operation==='quiz.start'&&result.output)group=result.output;if(body.operation==='tree.move'&&result.status==='ok')report.mutations.push({input:body.input,output:result.output});}catch{}});
const shot=async name=>page.screenshot({path:path.join(out,name+'.png')});
const check=(name,condition)=>{if(!condition)throw new Error(name);report.checks.push(name);};
const viewport=async()=>{const data=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,smallButtons:[...document.querySelectorAll('button')].filter(b=>{const r=b.getBoundingClientRect();return r.width>0&&r.height>0&&r.height<43.9;}).map(b=>b.textContent),katexErrors:document.querySelectorAll('.katex-error').length}));report.viewports.push(data);check('viewport '+data.width+' has no page overflow',data.scroll<=data.width);check('44px targets '+data.width,data.smallButtons.length===0);check('formulas render '+data.width,data.katexErrors===0);};
try{
 await page.route('**/api/agent',async route=>{if(route.request().postDataJSON().operation==='review.today')await new Promise(resolve=>setTimeout(resolve,600));await route.continue();});
 await page.goto(config.base,{waitUntil:'domcontentloaded'});await shot('mobile-loading');await page.locator('#today-tasks .empty').waitFor();await page.unroute('**/api/agent');
 check('entry has no manual question fields',await page.locator('math-field,textarea').count()===0);await shot('mobile-empty');
 await page.locator('#file-input').setInputFiles(config.image);await page.locator('#recognize-photo:not([disabled])').waitFor();await page.locator('#photo-boundary').scrollIntoViewIfNeeded();await shot('mobile-permission');
 await page.locator('#recognize-photo').click();await page.locator('#result .saved-card').waitFor();await shot('mobile-auto-result');
 await page.locator('#result .saved-card').waitFor();
 check('single click automatically creates verified wrong card',await page.locator('#result .saved-card').innerText().then(t=>t.includes('错题卡')));await shot('mobile-wrong-card');
 await page.locator('#result [data-quiz-card]').first().click();await page.locator('[data-quiz-answer]').first().waitFor();await shot('mobile-quiz-start');
 const student=await page.evaluate(()=>localStorage.getItem('mytree_demo'));
 const oracle=await page.request.get(config.base+'/__qa/answers?student='+encodeURIComponent(student)+'&quiz='+encodeURIComponent(group.quiz_id));const answers=await oracle.json();
 check('quiz has exactly three items with a transfer',group.items.length===3&&group.items.some(item=>item.is_transfer));
 check('quiz public response has no answers or hints',group.items.every(item=>!('answer_latex'in item)&&!('hints'in item)));
 for(let i=0;i<group.items.length;i++){
  const item=group.items[i],form=page.locator(`[data-quiz-answer="${item.id}"]`);
  await form.locator('math-field').evaluate((el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));},answers[item.id]);
  await form.locator('button').click();await page.locator(`[data-quiz-item="${item.id}"] [data-quiz-feedback]`).getByText('这题已通过，答题事实已保存。').waitFor();
  if(i===0){await shot('mobile-quiz-partial');const firstQuiz=group.quiz_id;await page.locator('[data-close-quiz]').click();await page.reload();await page.locator('[data-resume-quiz]').waitFor();await page.locator('[data-resume-quiz]').click();await page.locator('[data-quiz-answer]').first().waitFor();check('unfinished quiz resumes from server after reload',group.quiz_id===firstQuiz&&await page.locator('#quiz-answer-0').evaluate(el=>!!el.value));}
 }
 await page.locator('#quiz-summary .knowledge-card').waitFor();await page.locator('#quiz-summary').scrollIntoViewIfNeeded();await shot('mobile-unlocked');
 await page.locator('#unlocked-note').fill('先看两项是否都是平方。');await page.locator('[data-save-unlocked-note]').click();await page.locator('#unlocked-note-status').getByText('笔记已保存。').waitFor();
 await page.locator('[data-visit-tree]').click();await page.locator('[data-select-card]').first().waitFor();await page.locator('[data-select-card]').first().click();
 await page.locator('#tree-x').fill('20');await page.locator('#tree-y').fill('30');await page.locator('#tree-position button').click();await page.locator('[data-tree-card]').waitFor();
 const first=page.locator('[data-tree-card]').first();const box=await first.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+60,box.y+box.height/2+80,{steps:12});await page.mouse.up();
 await page.waitForFunction(()=>document.querySelector('#tree-action-status')?.textContent.includes('整理已保存'));
 await page.waitForTimeout(300);check('pointer drag persisted',report.mutations.some(item=>item.input.method==='drag'));
 await page.locator('[data-tree-card]').first().focus();await page.keyboard.press('ArrowRight');await page.waitForTimeout(500);
 check('keyboard move persisted',report.mutations.some(item=>item.input.method==='keyboard'));await page.locator('#tree-canvas').scrollIntoViewIfNeeded();await shot('mobile-keyboard-tree');await viewport();
 const after=report.mutations.at(-1).output.placement.position;
 await page.reload();await page.locator('[data-tree-card]').waitFor();check('position survives reload',await page.locator('#tree-x').inputValue()===String(after.x));
 check('knowledge note survives reload',await page.locator('#tree-note').inputValue()==='先看两项是否都是平方。');
 await page.locator('#tree-parent').selectOption('F2');await page.locator('#tree-x').fill('25');await page.locator('#tree-y').fill('45');await page.locator('#tree-position button').click();await page.waitForTimeout(350);
 check('menu move persisted',report.mutations.some(item=>item.input.method==='menu'&&item.input.parent_id==='F2'));
 await page.setViewportSize({width:1440,height:900});await page.locator('#tree-canvas').scrollIntoViewIfNeeded();await shot('desktop-tree');await viewport();
 await page.locator('[data-tree-undo]').click();await page.waitForTimeout(300);check('latest undo works',report.mutations.at(-1).input.action==='undo');
 check('score is own reference growth',await page.locator('.tree-growth').innerText().then(t=>t.includes('参考成长分')&&t.includes('小组未开启')&&t.includes('10')));
 await page.setViewportSize({width:390,height:844});
 await page.route('**/api/agent',async route=>{const b=route.request().postDataJSON();if(b.operation==='tree.get')return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'测试服务暂时不可用'}})});await route.continue();});
 await page.reload();await page.locator('#tree-content [role="alert"]').waitFor();await shot('mobile-error');check('error offers retry',await page.locator('[data-tree-retry]').count()===1);await page.unroute('**/api/agent');
 await page.locator('[data-tree-retry]').click();await page.locator('[data-tree-card]').waitFor();
 const saved=JSON.parse(fs.readFileSync(config.profile,'utf8'));
 const owned=saved[student];for(const task of Object.values(owned.reviews))task.due=new Date(Date.now()-86400000).toISOString();fs.writeFileSync(config.profile,JSON.stringify(saved));
 await page.goto(config.base);await page.locator('[data-today-task]').first().waitFor();check('today contains at most three concrete tasks',await page.locator('[data-today-task]').count()<=3);await shot('mobile-today');
 await page.locator('[data-snooze]').click();await page.locator('#review-focus').getByText('今天不再提醒，任务仍留在这里。').waitFor();check('snooze leaves the task accessible',await page.locator('[data-today-task]').count()>0);
 await page.locator('[data-today-task]').first().click();await page.locator('#review-focus [data-quiz-card]').click();await page.locator('[data-quiz-answer]').first().waitFor();
 const reviewQuiz=group;const reviewAnswers=await (await page.request.get(config.base+'/__qa/answers?student='+encodeURIComponent(student)+'&quiz='+encodeURIComponent(reviewQuiz.quiz_id))).json();
 for(const level of [1,2,3]){await page.locator('[data-quiz-item]').first().locator(`[data-quiz-hint="${level}"]`).click();await page.waitForTimeout(100);}
 for(const item of reviewQuiz.items){const form=page.locator(`[data-quiz-answer="${item.id}"]`);await form.locator('math-field').evaluate((el,value)=>{el.value=value;},reviewAnswers[item.id]);await form.locator('button').click();await form.locator('button').filter({hasText:'已保存'}).waitFor();}
 await page.locator('#quiz-summary').getByText('还差一点，先回顾再来。').waitFor();check('full solution hint prevents UI unlock',await page.locator('#quiz-summary').innerText().then(text=>text.includes('使用过完整解法')));await page.locator('#quiz-summary').scrollIntoViewIfNeeded();await shot('mobile-hint-blocked');
 check('no external asset requests',(await page.evaluate(()=>performance.getEntriesByType('resource').filter(x=>!x.name.startsWith(location.origin)).length))===0);
 const bare=await page.evaluate(()=>{const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),found=[];while(walker.nextNode()){const n=walker.currentNode,e=n.parentElement;if(e&&!e.closest('.katex,math-field,textarea,input,script,style')&&e.getClientRects().length&&/[\\^*]/.test(n.data))found.push(n.data);}return found;});check('no visible raw formula syntax',bare.length===0);
 check('no browser exceptions',report.errors.length===0);report.success=true;
}catch(error){report.failure=error.message;await shot('failure');process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();service.kill('SIGTERM');}
