import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.MYTREE_PLAYWRIGHT_PATH||'playwright');
const root=path.resolve(import.meta.dirname,'../..');
const out=path.join(root,'docs/evidence/junior');fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
const replay=process.env.MYTREE_QA_REPLAY==='1';
const reuseOCR=process.env.MYTREE_QA_REUSE_OCR==='1';
const report={mode:replay?'recorded-live-responses-layout-check':reuseOCR?'recorded-ocr-live-tutoring':'live-models',viewport:[],errors:[],responses:[],stages:[]};
if(replay){
 const original=JSON.parse(fs.readFileSync(path.join(out,'live-browser-results.json'),'utf8'));
 const queues=new Map();for(const r of original.responses){const q=queues.get(r.path)||[];q.push(r);queues.set(r.path,q);}
 await page.route('**/api/**',async route=>{const key=new URL(route.request().url()).pathname;const q=queues.get(key);if(!q?.length)throw new Error('Missing recorded endpoint '+key);const r=q.length>1?q.shift():q[0];await route.fulfill({status:r.status,contentType:'application/json',body:JSON.stringify(r.body)});});
}
if(reuseOCR){const cached=JSON.parse(fs.readFileSync(path.join(out,'gpt-ocr-response.json'),'utf8'));await page.route('**/api/recognize',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(cached)}));}
page.on('pageerror',error=>report.errors.push(error.message));
page.on('response',async response=>{if(response.url().includes('/api/')){try{report.responses.push({path:new URL(response.url()).pathname,status:response.status(),body:await response.json()});}catch{}}});
const snapshot=async name=>{await page.screenshot({path:path.join(out,name+'.jpg'),type:'jpeg',quality:85});report.stages.push(name);};
try{
 await page.goto('http://127.0.0.1:8000');await page.locator('#tree-preview').getByText('37',{exact:false}).waitFor();
 report.empty={mathFields:await page.locator('math-field').count(),textAreas:await page.locator('textarea').count(),manual:await page.getByText('手动录入',{exact:true}).count()};
 await snapshot('mobile-entry');
 await page.locator('#file-input').setInputFiles(path.join(root,'mytree/data/evaluation/calculation.jpg'));
 await page.locator('#recognize-photo:not([disabled])').waitFor();
 await page.locator('#recognize-photo').click();
 report.loading=await page.locator('#recognition-message').innerText();
 await page.locator('#confirm-ocr').waitFor({timeout:95000});
 report.review={fields:await page.locator('math-field').count(),text:await page.locator('#recognition-review').innerText()};
 await snapshot('mobile-formula-review');
 await page.locator('#confirm-ocr').click();
 await page.locator('#start-practice').waitFor({timeout:95000});
 report.analysis=report.responses.findLast(r=>r.path==='/api/study')?.body;
 if(report.analysis?.analysis?.status!=='correct')throw new Error('Correct photographed arithmetic was not fully verified: '+report.analysis?.analysis?.status);
 for(let i=0;i<3;i++)await page.locator(`[data-hint="${i}"]`).click();
 await page.locator('#hints').scrollIntoViewIfNeeded();await snapshot('mobile-math-hints');
 report.bareMath=await page.evaluate(()=>{const walker=document.createTreeWalker(document.querySelector('#result'),NodeFilter.SHOW_TEXT);const found=[];while(walker.nextNode()){const node=walker.currentNode,el=node.parentElement;if(el&&!el.closest('.katex,math-field,textarea,script,style')&&el.getClientRects().length&&/[\\^]|\u0000/.test(node.data))found.push(node.data);}return found;});
 if(report.bareMath.length)throw new Error('Unrendered mathematics: '+report.bareMath.join(' | '));
 await page.locator('[data-rating="confusing"]').click();
 await page.locator('#tutor-messages .teacher').waitFor({timeout:95000});
 report.chat=await page.locator('#tutor-messages').innerText();
 await page.locator('#start-practice').click();await page.locator('[data-exercise]').first().waitFor();
 const exerciseResponse=report.responses.findLast(r=>r.path==='/api/practice')?.body;
 for(const item of exerciseResponse.items){
  const matches=(item.question_md||item.question).match(/(\d+)\\times\s*(\d+)-(\d+)/);
  if(!matches)throw new Error('Unexpected N1 practice format');
  const answer=String(Number(matches[1])*Number(matches[2])-Number(matches[3]));
  await page.locator(`#answer-${item.id}`).evaluate((el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));},answer);
  const block=page.locator(`[data-exercise="${item.id}"]`);await block.locator('[data-check]').click();await block.locator('[data-check]').filter({hasText:'已做对'}).waitFor();
 }
 await page.locator('#practice-list').scrollIntoViewIfNeeded();await snapshot('mobile-practice');
 report.viewport.push(await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,unrendered:document.querySelectorAll('.math-pending').length,smallButtons:[...document.querySelectorAll('button')].filter(x=>{const r=x.getBoundingClientRect();return r.height>0&&r.height<44;}).map(x=>x.textContent),katex:document.querySelectorAll('.katex').length})));
 await page.setViewportSize({width:1440,height:900});await page.locator('#hints').scrollIntoViewIfNeeded();await snapshot('desktop-math-hints');
 report.viewport.push(await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,unrendered:document.querySelectorAll('.math-pending').length})));
 const safe=await page.evaluate(()=>{const e=document.createElement('div');e.innerHTML=MathUI.rich('公式 \\(\\frac{1}{2}\\) <script>window.mathInjected=true</script><img src=x onerror="window.mathInjected=true">[链接](javascript:alert(1))');document.body.append(e);const result={injected:!!window.mathInjected,unsafe:e.querySelectorAll('script,img,[href^="javascript"]').length,fraction:e.querySelectorAll('.mfrac').length};e.remove();return result;});report.sanitization=safe;
 await page.getByRole('link',{name:'知识树',exact:true}).click();await page.locator('.kp').first().waitFor();report.tree={nodes:await page.locator('.kp').count(),chapters:await page.locator('.chapter').count()};await snapshot('desktop-tree');
 await page.getByRole('link',{name:'家长看板',exact:true}).click();await page.locator('.event').first().waitFor();report.parent=await page.locator('#parent-content').innerText();
 const profile=report.responses.findLast(r=>r.path==='/api/profile')?.body;report.progress={practiceCorrect:profile?.practice_correct,feedbackCount:profile?.feedback_count,reviews:profile?.reviews?.length};
 report.external=await page.evaluate(()=>performance.getEntriesByType('resource').filter(x=>!x.name.startsWith(location.origin)).map(x=>x.name));
 report.success=true;
}catch(error){report.failure=error.message;await snapshot('failure');process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({success:report.success,failure:report.failure,empty:report.empty,viewport:report.viewport,errors:report.errors,tree:report.tree,progress:report.progress,sanitization:report.sanitization}));await browser.close();}
