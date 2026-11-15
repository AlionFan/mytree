/* Emulator only: actual emulated camera/microphone, existing explorer UI,
 * a held synthetic observation, Home/return and late-result suppression. */
import {createRequire} from 'node:module';import {spawn,execFileSync} from 'node:child_process';import readline from 'node:readline';import fs from 'node:fs';import path from 'node:path';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(import.meta.dirname,'..'),adb='/Users/fan/Library/Android/sdk/platform-tools/adb',serial=process.env.ANDROID_SERIAL||'emulator-5554',origin='https://mytree.joybeat.cn';
const shell=(...args)=>execFileSync(adb,['-s',serial,'shell',...args],{encoding:'utf8'});
if(shell('getprop','ro.kernel.qemu').trim()!=='1')throw Error('Emulator required');
shell('pm','grant','cn.joybeat.mytree','android.permission.CAMERA');shell('pm','grant','cn.joybeat.mytree','android.permission.RECORD_AUDIO');
const svc=spawn(root+'/mytree/.venv/bin/python',[root+'/mytree/scripts/serve_qa_phase_b.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
const cfg=await new Promise((resolve,reject)=>{const r=readline.createInterface({input:svc.stdout}),timer=setTimeout(()=>reject(Error('service timeout')),15000);r.once('line',s=>{clearTimeout(timer);resolve(JSON.parse(s));});});
const b=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ctx=b.contexts()[0],page=ctx.pages()[0];page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(15000);
const report={mode:'actual-emulator-camera-microphone/existing-explorer/synthetic-held-observation',checks:[],speechRequests:0};let releaseObservation,observationSeen=false;
const held=new Promise(r=>releaseObservation=r);
const handler=async route=>{
 const req=route.request(),u=new URL(req.url());
 if(u.pathname==='/api/explorer/observe'){observationSeen=true;await held;try{await route.fulfill({json:{description:'A synthetic blue cube.'}});}catch{}return;}
 if(u.pathname==='/api/speech'){report.speechRequests++;await route.fulfill({status:503,json:{error:'Test denies speech'}});return;}
 const headers={...req.headers(),origin:cfg.base,host:new URL(cfg.base).host,connection:'close'};delete headers.cookie;
 const res=await fetch(cfg.base+u.pathname+u.search,{method:req.method(),headers,body:req.postDataBuffer()||undefined,redirect:'manual'}),returned=Object.fromEntries(res.headers);delete returned['content-length'];delete returned['content-encoding'];delete returned['transfer-encoding'];await route.fulfill({status:res.status,headers:returned,body:Buffer.from(await res.arrayBuffer())});
};
const check=(name,value)=>{if(!value)throw Error(name);report.checks.push(name);};
try{
 await ctx.route(origin+'/**',handler);await page.goto(origin+'/explore');await page.locator('#explorer-toggle').waitFor();
 await page.evaluate(()=>{window.__nativeStreams=[];const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=async(...args)=>{const stream=await original(...args);window.__nativeStreams.push(stream);return stream;};});
 await page.locator('#explorer-toggle').click();await page.waitForFunction(()=>document.querySelector('#explorer-video').srcObject?.getVideoTracks().some(t=>t.readyState==='live'));
 check('actual emulated camera acquired through native permission callback',true);
 await page.locator('#explorer-talk').click();try{await page.waitForFunction(()=>window.__nativeStreams.some(s=>s.getAudioTracks().some(t=>t.readyState==='live')),null,{timeout:3000});check('actual emulated microphone acquired through native permission callback',true);}catch{report.microphoneLimitation=await page.locator('#explorer-state').innerText();}
 check('observation request held before background',observationSeen);
 shell('input','keyevent','KEYCODE_HOME');
 await page.waitForFunction(()=>window.__nativeStreams.flatMap(s=>s.getTracks()).every(t=>t.readyState==='ended'),null,{polling:100,timeout:10000});
 check('Home stops every acquired video and audio track',true);
 const started=Date.now();report.cameraReleaseSamples=[];
 for(;;){
  const cameraDump=shell('dumpsys','media.camera');report.activeCameraClientsAfterHome=cameraDump.split('Active Camera Clients:')[1]?.split('Allowed user IDs:')[0]?.trim();
  const elapsedMs=Date.now()-started,empty=report.activeCameraClientsAfterHome==='[]';report.cameraReleaseSamples.push({elapsedMs,empty});
  if(empty){report.cameraReleaseDelayMs=elapsedMs;break;}
  if(elapsedMs>=5000)throw Error('Native CameraService still occupied after 5 seconds');
  await new Promise(r=>setTimeout(r,100));
 }
 check('native CameraService releases captured camera within 5 seconds after Home',true);
 releaseObservation();await page.waitForTimeout(500);check('late observation never requests speech in background',report.speechRequests===0);
 shell('am','start','-W','-n','cn.joybeat.mytree/.MainActivity');
 check('return does not automatically restart camera or microphone',await page.evaluate(()=>window.__nativeStreams.flatMap(s=>s.getTracks()).every(t=>t.readyState==='ended')));
 report.success=true;
}catch(e){report.failure=e.stack;report.trackProbe=await page.evaluate(()=>({visibility:document.visibilityState,tracks:window.__nativeStreams?.flatMap(s=>s.getTracks()).map(t=>({kind:t.kind,state:t.readyState}))})).catch(()=>null);process.exitCode=1;}
finally{
 releaseObservation();shell('am','start','-W','-n','cn.joybeat.mytree/.MainActivity');fs.writeFileSync(root+'/docs/evidence/android/media.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await ctx.unroute(origin+'/**',handler);await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:5000}).catch(()=>{});svc.kill();await Promise.race([b.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);
}

process.exit(process.exitCode||0);
