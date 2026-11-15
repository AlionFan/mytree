/* Runs only on an Android emulator. Routes the trusted origin to the existing
 * isolated QA service: synthetic photo, fake upstream, real business handlers.
 * Does not send photos to the production site or invoke paid models. */
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
import readline from 'node:readline';
const require=createRequire(import.meta.url);
const {chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(import.meta.dirname,'..'),origin='https://mytree.joybeat.cn';
const adb=process.env.ANDROID_ADB||'/Users/fan/Library/Android/sdk/platform-tools/adb';
const serial=process.env.ANDROID_SERIAL||'emulator-5554';
if(execFileSync(adb,['-s',serial,'shell','getprop','ro.kernel.qemu'],{encoding:'utf8'}).trim()!=='1')throw Error('Emulator required; never use a personal device/session');
const svc=spawn(path.join(root,'mytree/.venv/bin/python'),[path.join(root,'mytree/scripts/serve_qa_phase_b.py')],{cwd:root,stdio:['ignore','pipe','pipe']});
const cfg=await new Promise((resolve,reject)=>{const r=readline.createInterface({input:svc.stdout}),timer=setTimeout(()=>reject(Error('QA service timeout')),15000);r.once('line',s=>{clearTimeout(timer);try{resolve(JSON.parse(s));}catch(e){reject(e);}});svc.once('error',reject);});
if(!cfg.profile.startsWith('/var/folders/')&&!cfg.profile.startsWith('/tmp/'))throw Error('Temporary profile required');
const out=path.join(root,'docs/evidence/android/webview');fs.mkdirSync(out,{recursive:true});
const report={mode:'actual-Android-WebView-emulator/synthetic-photo/fake-upstream/real-business-http',checks:[],errors:[],mutations:[]};
const browser=await chromium.connectOverCDP(process.env.ANDROID_WEBVIEW_CDP||'http://127.0.0.1:9224',{noDefaults:true});
const ctx=browser.contexts()[0],page=ctx.pages()[0];
page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(15000);
let group=null;
const check=(name,value)=>{if(!value)throw Error(name);report.checks.push(name);};
const shot=name=>page.screenshot({path:path.join(out,name+'.png')});
const routeHandler=async route=>{
 const request=route.request(),u=new URL(request.url());
 const headers={...request.headers(),origin:cfg.base,host:new URL(cfg.base).host,connection:'close'};delete headers.cookie;
 try{
  const response=await fetch(cfg.base+u.pathname+u.search,{method:request.method(),headers,body:request.postDataBuffer()||undefined,redirect:'manual'});
  const returnedHeaders=Object.fromEntries(response.headers);delete returnedHeaders['content-length'];delete returnedHeaders['transfer-encoding'];delete returnedHeaders['content-encoding'];
  await route.fulfill({status:response.status,headers:returnedHeaders,body:Buffer.from(await response.arrayBuffer())});
 }catch(e){report.errors.push('proxy '+request.method()+' '+u.pathname+': '+e.message+' '+(e.cause?.code||''));await route.abort();}
};
page.on('pageerror',e=>report.errors.push(e.message));
page.on('response',async response=>{try{const req=response.request();if(new URL(response.url()).pathname!=='/api/agent'||req.method()!=='POST')return;const body=req.postDataJSON(),value=await response.json();if(body.operation==='quiz.start'&&value.output)group=value.output;if(body.operation==='tree.move'&&value.status==='ok')report.mutations.push(body.input);}catch{}});
try{
 await ctx.route(origin+'/**',routeHandler);
 await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
 await page.locator('#file-input').waitFor({state:'attached'});
 check('actual WebView trusted-origin learning page',await page.locator('#open-camera').count()===1);
 check('no horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await shot('01-learning');
 await page.locator('#file-input').setInputFiles(cfg.image);
 await page.locator('#recognize-photo:not([disabled])').waitFor();await shot('02-preview');
 await page.locator('#recognize-photo').click();await page.locator('#result .current-question').waitFor();
 check('synthetic OCR auto creates verified wrong card',(await page.locator('#result .result-status').innerText()).includes('错题卡'));
 await shot('03-wrong-card');
 await page.locator('#result [data-quiz-card]').first().click();await page.locator('[data-quiz-answer]').first().waitFor();
 const student=await page.evaluate(()=>localStorage.getItem('mytree_demo'));
 const response=await fetch(cfg.base+'/__qa/answers?student='+encodeURIComponent(student)+'&quiz='+encodeURIComponent(group.quiz_id)),answers=await response.json();
 check('three service-generated quiz items',group.items.length===3);
 check('quiz excludes private answers',group.items.every(i=>!('answer_latex'in i)&&!('hints'in i)));
 for(const item of group.items){const form=page.locator(`[data-quiz-answer="${item.id}"]`);for(let turn=0;turn<3&&!(await form.isVisible());turn++)await page.locator('#quiz-dialog .focus-pager').getByRole('button',{name:'下一页',exact:true}).click();await form.locator('math-field').evaluate((el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));},answers[item.id]);await form.locator('button').click();await page.locator(`[data-quiz-item="${item.id}"] [data-quiz-feedback]`).getByText('这题已通过，答题事实已保存。').waitFor({state:'attached'});}
 await page.locator('#quiz-summary .knowledge-card').waitFor();check('knowledge card unlocked after quiz',true);await shot('04-unlocked');
 await page.locator('[data-visit-tree]').click();await page.locator('[data-select-card]').first().waitFor();await page.locator('[data-select-card]').first().click();await page.locator('#knowledge-lesson[open]').waitFor();execFileSync(adb,['-s',serial,'shell','uiautomator','dump','/sdcard/hks-back-check.xml']);report.nativeConfirmationBeforeBack=execFileSync(adb,['-s',serial,'shell','cat','/sdcard/hks-back-check.xml'],{encoding:'utf8'}).includes('在浏览器中打开？');check('no stale native confirmation covers actual knowledge dialog',!report.nativeConfirmationBeforeBack);execFileSync(adb,['-s',serial,'shell','input','keyevent','KEYCODE_BACK']);await page.locator('#knowledge-lesson[open]').waitFor({state:'hidden'});check('native Back closes knowledge dialog before navigation',true);await page.locator('[data-edit-selected]').click();await page.locator('#tree-x').fill('20');await page.locator('#tree-y').fill('30');await page.locator('#tree-position button').click();await page.locator('[data-tree-card]').first().waitFor();
 // Use actual CDP touch input on the emulator WebView, not a desktop viewport.
 const client=await ctx.newCDPSession(page),card=page.locator('[data-tree-card]').first();await card.scrollIntoViewIfNeeded();const box=await card.boundingBox();
 const x=box.x+box.width/2,y=box.y+box.height/2;
 const dragResponse=page.waitForResponse(r=>{try{return new URL(r.url()).pathname==='/api/agent'&&r.request().postDataJSON().operation==='tree.move'&&r.request().postDataJSON().input.method==='drag';}catch{return false;}});
 await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:1,x,y,radiusX:4,radiusY:4}]});
 for(let i=1;i<=8;i++)await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{id:1,x:x+30*i/8,y:y+35*i/8,radiusX:4,radiusY:4}]});
 await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await page.waitForFunction(()=>document.querySelector('#tree-action-status')?.textContent.includes('整理已保存'));
 const dragResult=await(await dragResponse).json();check('touch tree move persisted by business service',dragResult.status==='ok');
 await shot('05-tree');await page.reload();await page.locator('[data-tree-card]').waitFor();
 check('tree reload restores card',(await page.locator('[data-tree-card]').count())===1);
 check('no JS/proxy errors',report.errors.length===0);report.success=true;
}catch(e){report.failure=e.stack;process.exitCode=1;try{await shot('failure');}catch{}}
finally{
 report.browserVersion=browser.version();report.viewport=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scale:devicePixelRatio})).catch(()=>null);
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));
 await ctx.unroute(origin+'/**',routeHandler);await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:5000}).catch(()=>{});
 await Promise.race([browser.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);svc.kill();
}
console.log(JSON.stringify({success:report.success,checks:report.checks.length,failure:report.failure}));

process.exit(process.exitCode||0);
