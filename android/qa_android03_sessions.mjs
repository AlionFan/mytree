// Uses isolated seeded email sessions (no emails are sent). Exercises actual
// WebView HttpOnly Cookie behavior, service ownership, logout and parent next.
import {createRequire} from 'node:module';import {spawn,execFileSync} from 'node:child_process';import readline from 'node:readline';import fs from 'node:fs';import path from 'node:path';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(import.meta.dirname,'..'),adb='/Users/fan/Library/Android/sdk/platform-tools/adb',serial=process.env.ANDROID_SERIAL||'emulator-5554',origin='https://mytree.joybeat.cn';
if(execFileSync(adb,['-s',serial,'shell','getprop','ro.kernel.qemu'],{encoding:'utf8'}).trim()!=='1')throw Error('Emulator required');
const svc=spawn(root+'/mytree/.venv/bin/python',[root+'/mytree/scripts/serve_qa_product.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
const cfg=await new Promise((resolve,reject)=>{const r=readline.createInterface({input:svc.stdout}),timer=setTimeout(()=>reject(Error('service timeout')),15000);r.once('line',s=>{clearTimeout(timer);resolve(JSON.parse(s));});});
const b=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ctx=b.contexts()[0],page=ctx.pages()[0],cdp=await ctx.newCDPSession(page);page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(15000);
const report={mode:'actual-emulator-WebView/seeded-synthetic-email-sessions/isolated-service',checks:[]};
const handler=async route=>{
 const req=route.request(),u=new URL(req.url()),headers={...req.headers(),origin:cfg.base,host:new URL(cfg.base).host,connection:'close'};
 const res=await fetch(cfg.base+u.pathname+u.search,{method:req.method(),headers,body:req.postDataBuffer()||undefined,redirect:'manual'}),returned=Object.fromEntries(res.headers);delete returned['content-length'];delete returned['content-encoding'];delete returned['transfer-encoding'];await route.fulfill({status:res.status,headers:returned,body:Buffer.from(await res.arrayBuffer())});
};
const check=(n,v)=>{if(!v)throw Error(n);report.checks.push(n);};
const cookie=async i=>cdp.send('Network.setCookie',{name:'mytree_session',value:cfg.users[i].token,url:origin+'/',secure:true,httpOnly:true,sameSite:'Strict'});
const me=()=>page.evaluate(async()=>{const r=await fetch('/api/auth/me');return {status:r.status,data:await r.json()};});
try{
 await ctx.route(origin+'/**',handler);
 await cdp.send('Network.deleteCookies',{name:'mytree_session',url:origin+'/'});await page.goto(origin+'/parent');
 check('anonymous parent entry keeps login next',page.url().includes('/login')&&page.url().includes('parent'));
 await cookie(0);await page.goto(origin+'/tree');
 if(await page.locator('#usage-guide[open]').count())await page.locator('[data-close-guide]').first().click();
 await page.locator('[data-tree-card]').waitFor();check('learner cookie loads learner knowledge tree',true);
 check('HttpOnly session unavailable to document.cookie',!(await page.evaluate(()=>document.cookie)).includes('mytree_session'));
 const learner=await me();check('same-origin fetch sends actual WebView cookie',learner.status===200);
 await page.evaluate(async()=>{await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});});
 const loggedOut=await me();check('logout revokes session in service',loggedOut.status===401);
 await page.waitForURL(/\/login/,{waitUntil:'domcontentloaded',timeout:3000}).catch(()=>{});await page.goto(origin+'/tree',{waitUntil:'domcontentloaded'}).catch(e=>{if(!page.url().includes('/login'))throw e;});await page.waitForURL(/\/login/);check('logged-out private route redirects to login',page.url().includes('/login'));
 await cookie(2);await page.goto(origin+'/tree');
 if(await page.locator('#usage-guide[open]').count())await page.locator('[data-close-guide]').first().click();
 await page.locator('.tree-card-count').waitFor();check('different session cannot see learner tree',(await page.locator('[data-tree-card]').count())===0);
 report.success=true;
}catch(e){report.failure=e.stack;process.exitCode=1;}
finally{
 fs.writeFileSync(root+'/docs/evidence/feedback-1115/android03/sessions.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await cdp.send('Network.deleteCookies',{name:'mytree_session',url:origin+'/'}).catch(()=>{});await ctx.unroute(origin+'/**',handler);await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:5000}).catch(()=>{});svc.kill();await Promise.race([b.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);
}

process.exit(process.exitCode||0);
