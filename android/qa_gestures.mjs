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
const out=path.join(root,'docs/evidence/android/gestures');fs.mkdirSync(out,{recursive:true});
const report={mode:'actual-Android-WebView-emulator/touch-input/synthetic-long-page-and-PDF',checks:[],errors:[],mutations:[]};
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
 const longdir=fs.mkdtempSync('/tmp/hks-android-gesture-'),photo=path.join(longdir,'long.png');
 execFileSync(path.join(root,'mytree/.venv/bin/python'),['-c',"from PIL import Image,ImageDraw;import sys;p=Image.new('RGB',(600,1600),'white');d=ImageDraw.Draw(p);[(d.line((0,y,600,y),fill='gray'),d.text((25,y+10),'Synthetic worksheet '+str(y),fill='black')) for y in range(0,1600,100)];p.save(sys.argv[1])",photo]);
 const ready=async()=>{await page.goto(origin+'/',{waitUntil:'domcontentloaded'});await page.locator('#file-input').setInputFiles(photo);await page.locator('#recognize-photo:not([disabled])').waitFor();};
 const client=await ctx.newCDPSession(page),point=(id,x,y)=>({id,x,y,radiusX:4,radiusY:4}),touch=(type,touchPoints)=>client.send('Input.dispatchTouchEvent',{type,touchPoints});
 await ready();const positions=await page.locator('.document-preview').evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x+110,y:r.y+r.height/2,top:e.scrollTop};});
 await touch('touchStart',[point(1,positions.x,positions.y),point(2,positions.x+70,positions.y)]);
 await touch('touchMove',[point(1,positions.x,positions.y-100),point(2,positions.x+70,positions.y-100)]);await touch('touchEnd',[]);
 check('two fingers scroll actual Android WebView long source',await page.locator('.document-preview').evaluate((e,old)=>e.scrollTop>old,positions.top));
 check('two-finger browsing never creates crop',(await page.locator('#crop-status').innerText())==='整页识别');await shot('long-pan');
 const pos=await page.locator('.document-preview').evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x+100,y:r.y+r.height/2};});
 await touch('touchStart',[point(1,pos.x,pos.y)]);await touch('touchMove',[point(1,pos.x+60,pos.y+60)]);await touch('touchEnd',[]);
 await page.waitForFunction(()=>document.querySelector('#crop-status').textContent==='已选择一个区域');check('single-finger selection works after two-finger browsing',true);await shot('single-crop');
 let sent;await page.route('**/api/recognize/page',async route=>{sent=route.request().postDataJSON();await route.fallback();});
 await page.locator('#recognize-photo').click();await page.locator('#result .current-question').waitFor();
 const dimensions=await page.evaluate(async data=>{const image=new Image();image.src=data;await image.decode();return {width:image.naturalWidth,height:image.naturalHeight};},sent.image_data);
 report.cropPixels=dimensions;check('selection sends cropped source pixels',dimensions.width<600&&dimensions.height<1600&&dimensions.width>32&&dimensions.height>32);await page.unroute('**/api/recognize/page');
 await page.goto(origin+'/',{waitUntil:'domcontentloaded'});await page.locator('#file-input').setInputFiles(path.join(root,'mytree/tests/fixtures/worksheet.pdf'));await page.locator('#next-page:not([disabled])').waitFor();await page.locator('#next-page').click();await page.waitForFunction(()=>document.querySelector('#pdf-page').value==='2'&&!document.querySelector('#recognize-photo').disabled);
 check('PDF uploads and switches current page in actual WebView',true);check('PDF page has no horizontal overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await shot('pdf-page2');
 check('no JavaScript or proxy errors',report.errors.length===0);report.success=true;fs.rmSync(longdir,{recursive:true,force:true});

}catch(e){report.failure=e.stack;process.exitCode=1;try{await shot('failure');}catch{}}
finally{
 report.browserVersion=browser.version();report.viewport=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scale:devicePixelRatio})).catch(()=>null);
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2));
 await ctx.unroute(origin+'/**',routeHandler);await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:5000}).catch(()=>{});
 await Promise.race([browser.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);svc.kill();
}
console.log(JSON.stringify({success:report.success,checks:report.checks.length,failure:report.failure}));

process.exit(process.exitCode||0);
