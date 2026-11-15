/* Real model calls use only generated shapes and synthetic English audio. */
import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';
if(process.env.MYTREE_VERIFY_LIVE!=='1')throw new Error('Set MYTREE_VERIFY_LIVE=1 to verify live models using synthetic inputs.');
const require=createRequire(import.meta.url),{chromium}=require(process.env.MYTREE_PLAYWRIGHT_PATH||'/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(import.meta.dirname,'../..'),auth=JSON.parse(fs.readFileSync(path.join(root,'mytree/data/deployment/access.json'),'utf8'));
const out=path.join(root,'docs/evidence/explorer-release'),wav=fs.readFileSync(path.join(out,'synthetic-english.wav')).toString('base64');
const browser=await chromium.launch({headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const report={url:auth.url,real_model_calls:true,physical_devices:false,inputs:'synthetic shapes and OS-generated English only',speech_playback:'browser adapter; physical speaker not verified',checks:[],errors:[]};
const check=(name,ok)=>{if(!ok)throw new Error(name);report.checks.push(name);};
const context=await browser.newContext({httpCredentials:{username:auth.username,password:auth.password,origin:auth.url},viewport:{width:390,height:844}}),page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
try{
 const unauth=await browser.newContext();let r=await unauth.request.get(auth.url+'/api/capabilities');check('anonymous API is denied',r.status()===401);r=await unauth.request.post(auth.url+'/api/speech',{data:{action:'speak',text:'Hello.'}});check('anonymous model spending is denied',r.status()===401);await unauth.close();
 await page.addInitScript(({wav})=>{
  window.__tracks=[];
  window.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};
  Object.defineProperty(window,'speechSynthesis',{value:{getVoices:()=>[{lang:'en-US',name:'QA playback adapter',localService:true}],speak(u){window.__said=u.text;},cancel(){}},configurable:true});
  navigator.mediaDevices.getUserMedia=async constraints=>{
   let stream;
   if(constraints.video){const c=document.createElement('canvas');c.width=640;c.height=360;const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,640,360);ctx.fillStyle='green';ctx.fillRect(70,80,220,220);ctx.fillStyle='blue';ctx.beginPath();ctx.arc(460,190,80,0,Math.PI*2);ctx.fill();stream=c.captureStream(10);setTimeout(()=>ctx.fillRect(459,189,1,1),100);}
   else{const ctx=new AudioContext();await ctx.resume();const data=Uint8Array.from(atob(wav),x=>x.charCodeAt(0));const buffer=await ctx.decodeAudioData(data.buffer),source=ctx.createBufferSource(),dest=ctx.createMediaStreamDestination();source.buffer=buffer;source.connect(dest);source.start(ctx.currentTime+.3);stream=dest.stream;}
   window.__tracks.push(...stream.getTracks());return stream;
  };
 },{wav});
 await page.goto(auth.url+'/explore');await page.locator('#explorer-toggle').waitFor();check('trusted HTTPS explorer loads',page.url().startsWith('https:'));
 await page.locator('#explorer-toggle').click();await page.waitForFunction(()=>document.querySelector('#explorer-indicator').textContent==='英语播报',{},{timeout:90000});
 report.description=await page.locator('#explorer-caption').innerText();check('live camera description is English and grounded in synthetic shapes',/green|blue|rectangle|circle/i.test(report.description)&&!/[\u3400-\u9fff]/.test(report.description));
 await page.keyboard.press('Space');check('live deployed pause responds',await page.locator('#explorer-indicator').innerText()==='已打断');
 await page.keyboard.down('KeyV');await page.waitForFunction(()=>document.querySelector('#explorer-indicator').textContent==='正在录音');await page.waitForTimeout(3400);await page.keyboard.up('KeyV');
 await page.waitForFunction(()=>document.querySelector('#explorer-history').textContent.includes('English reply'),{},{timeout:90000});report.transcription=await page.locator('#explorer-question').inputValue();report.reply=await page.locator('#explorer-caption').innerText();
 check('live ASR receives synthetic speech through MediaRecorder',/tree|notebook/i.test(report.transcription));check('live contextual answer returns English',report.reply.length>0&&!/[\u3400-\u9fff]/.test(report.reply));
 await page.screenshot({path:path.join(out,'online-mobile-explorer.png')});await page.locator('#explorer-sleep').click();check('deployed stop closes media tracks',await page.evaluate(()=>__tracks.every(t=>t.readyState==='ended')));
 const assets=['/app.js','/explorer.js','/math-ui.js','/learning-ui.js','/style.css'];for(const asset of assets){const response=await context.request.get(auth.url+asset);check('deployed asset '+asset,response.status()===200);}
 const status=await context.request.get(auth.url+'/api/capabilities');const caps=await status.json();report.models={vision:caps.vision_model,asr:caps.asr_model};check('deployed selected model is retained',caps.vision_model==='gpt-6.1-sol');
 check('no browser exceptions',report.errors.length===0);report.success=true;
}catch(error){report.failure=error.message;await page.screenshot({path:path.join(out,'online-failure.png')});process.exitCode=1;}
finally{fs.writeFileSync(path.join(out,'online-browser.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();}
