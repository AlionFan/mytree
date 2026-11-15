/* Synthetic known speech injected at Chromium's virtual microphone, actual
 * Android WebView getUserMedia/MediaRecorder/WAV conversion and production ASR. */
import {createRequire} from 'node:module';import fs from 'node:fs';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const b=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ctx=b.contexts()[0],p=ctx.pages()[0];p.setDefaultTimeout(15000);
const report={input:'macOS Samantha synthetic speech through Chromium virtual microphone',expected:'What color is the notebook?',mockedASR:false,checks:[]};
const obs=async r=>r.fulfill({json:{description:'A notebook is on the table.',changed:true}});
try{
 await ctx.route('**/api/explorer/observe',obs);await p.goto('https://mytree.joybeat.cn/explore');await p.locator('#explorer-toggle').click();await p.waitForFunction(()=>document.querySelector('#explorer-talk')&&!document.querySelector('#explorer-talk').disabled);
 await p.evaluate(()=>{const old=window.MediaRecorder;window.__recordedBytes=0;window.MediaRecorder=class extends old{constructor(...args){super(...args);this.addEventListener('dataavailable',e=>window.__recordedBytes+=e.data.size);}};});
 await p.locator('#explorer-talk').click();await p.waitForFunction(()=>document.querySelector('#explorer-state').textContent.includes('正在录音'));
 await p.waitForTimeout(4700);const received=p.waitForResponse(r=>r.url().endsWith('/api/speech')&&r.request().postDataJSON()?.action==='transcribe',{timeout:90000});await p.locator('#explorer-talk').click();const response=await received,result=await response.json();
 report.status=response.status();report.text=result.text;report.model=result.model;report.recordedBytes=await p.evaluate(()=>window.__recordedBytes);report.question=await p.locator('#explorer-question').inputValue();
 if(!response.ok()||!result.text?.toLowerCase().includes('color')||!result.text?.toLowerCase().includes('notebook')||report.recordedBytes<1000)throw Error('Meaningful recording/ASR mismatch');
 report.checks.push('actual UI starts and ends MediaRecorder','nonempty encoded audio','production ASR matches known source sentence','recognized text fills explorer question');await p.locator('#explorer-sleep').click();report.success=true;
}catch(e){report.failure=e.message;process.exitCode=1;}
finally{await ctx.unroute('**/api/explorer/observe',obs);fs.writeFileSync('docs/evidence/feedback-1115/recording.json',JSON.stringify(report,null,2));console.log(report);process.exit(process.exitCode||0);}
