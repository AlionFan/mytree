import {createRequire} from 'node:module';import {spawn} from 'node:child_process';import readline from 'node:readline';import fs from 'node:fs';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const svc=spawn('mytree/.venv/bin/python',['mytree/scripts/serve_qa_feedback.py'],{env:{...process.env,MYTREE_MEM0_ENABLED:'0'}}),cfg=await new Promise(r=>readline.createInterface({input:svc.stdout}).once('line',l=>r(JSON.parse(l))));
const android=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ac=android.contexts()[0],ap=ac.pages()[0],origin='https://mytree.joybeat.cn';
const viewport=await ap.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio}));
const web=await chromium.launch(),wc=await web.newContext({viewport:{width:viewport.width,height:viewport.height},deviceScaleFactor:viewport.dpr}),wp=await wc.newPage();
const report={viewport,mode:'same shared source and CSS viewport; browser Chromium vs installed APK Android15 WebView; synthetic page, no paid AI',checks:[]},check=(n,v)=>{if(!v)throw Error(n);report.checks.push(n)};
const proxy=async route=>{const q=route.request(),u=new URL(q.url()),headers={...q.headers(),host:new URL(cfg.base).host,origin:cfg.base,connection:'close'};delete headers.cookie;const r=await fetch(cfg.base+u.pathname+u.search,{method:q.method(),headers,body:q.postDataBuffer()||undefined,redirect:'manual'}),h=Object.fromEntries(r.headers);for(const k of ['content-length','content-encoding','transfer-encoding'])delete h[k];await route.fulfill({status:r.status,headers:h,body:Buffer.from(await r.arrayBuffer())});};
async function learn(p){
 p.setDefaultTimeout(25000);await p.addInitScript(()=>localStorage.setItem('mytree_demo','demo'));await p.goto(origin);await p.locator('[data-focus-switch="desk"]').first().waitFor();if(await p.locator('#usage-guide[open]').count())await p.locator('[data-close-guide]').first().click();
 await p.locator('#file-input').setInputFiles(cfg.image);await p.locator('#recognize-photo').click();await p.waitForFunction(()=>document.querySelectorAll('[data-open-reading]').length===10,null,{timeout:40000});await p.locator('[data-question-chooser]').click();const d=p.locator('dialog[data-reading-chooser]');for(let i=0;i<7;i++)await d.locator('.focus-pager button').last().click();await d.locator('[data-open-reading]:visible').click();await p.waitForFunction(()=>document.querySelector('.question-counter')?.textContent==='8 / 10');await p.evaluate(()=>document.fonts.ready);
}
async function metrics(p){return p.evaluate(()=>{
 const result={};for(const sel of ['.capture-secondary','.question-counter','[data-question-chooser]','.current-question','.result-tabs']){
  const el=document.querySelector(sel),r=el.getBoundingClientRect(),s=getComputedStyle(el);result[sel]={x:r.x,y:r.y,w:r.width,h:r.height,position:s.position,font:s.fontFamily,size:s.fontSize,text:el.innerText};
 }
 result.math={total:document.querySelector('.current-question').querySelectorAll('math').length,sup:document.querySelector('.current-question').querySelectorAll('msup').length,plain:document.querySelector('.current-question').querySelectorAll('.math-plain').length};
 return result;
})}
try{
 await ac.route(origin+'/**',proxy);await wc.route(origin+'/**',proxy);await learn(ap);await learn(wp);const am=await metrics(ap),wm=await metrics(wp);report.android=am;report.web=wm;
 check('floating toolbar is absolute on both',am['.capture-secondary'].position==='absolute'&&wm['.capture-secondary'].position==='absolute');
 for(const sel of ['.capture-secondary','.question-counter','[data-question-chooser]','.current-question','.result-tabs']){
  check(sel+' text and font agree',am[sel].text===wm[sel].text&&am[sel].font===wm[sel].font&&am[sel].size===wm[sel].size);
  check(sel+' layout agrees within six CSS pixels',['x','y','w','h'].every(k=>Math.abs(am[sel][k]-wm[sel][k])<=6));
 }
 check('rendered exponents on both',am.math.sup>0&&wm.math.sup>0&&am.math.plain===0&&wm.math.plain===0);
 await ap.screenshot({path:'docs/evidence/mem0-personal-review/consistency-android-floating.png'});await wp.screenshot({path:'docs/evidence/mem0-personal-review/consistency-web-floating.png'});
 for(const [p,name] of [[ap,'android'],[wp,'web']]){
  await p.locator('[data-focus-switch="desk"][data-value="cards"]').click();await p.locator('.stored-wrong:visible math').first().waitFor();check(name+' saved cards use fractions and superscripts',await p.locator('.stored-wrong:visible math').count()>0);
  await p.screenshot({path:'docs/evidence/mem0-personal-review/consistency-'+name+'-cards.png'});
  await p.goto(origin+'/plan');await p.locator('#personalize-plan').waitFor();check(name+' same personalized review action',await p.locator('#personalize-plan').innerText()==='更新个性化复习');
 }
 report.success=true;
}catch(error){report.failure=error.stack;await ap.screenshot({path:'docs/evidence/mem0-personal-review/consistency-failure.png'}).catch(()=>{});process.exitCode=1}
finally{fs.writeFileSync('docs/evidence/mem0-personal-review/consistency-results.json',JSON.stringify(report,null,2));console.log({success:report.success,checks:report.checks.length,failure:report.failure});await ac.unroute(origin+'/**',proxy).catch(()=>{});await ap.goto(origin+'/login').catch(()=>{});await web.close();svc.kill();process.exit(process.exitCode||0)}
