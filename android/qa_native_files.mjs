// Guided emulator-only native camera and DocumentsUI return test. While this
// process waits, operate the system UI through adb using observed UI bounds.
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const adb='/Users/fan/Library/Android/sdk/platform-tools/adb',serial=process.env.ANDROID_SERIAL||'emulator-5554';
if(execFileSync(adb,['-s',serial,'shell','getprop','ro.kernel.qemu'],{encoding:'utf8'}).trim()!=='1')throw Error('Emulator required');
execFileSync(adb,['-s',serial,'shell','pm','grant','cn.joybeat.mytree','android.permission.CAMERA']);
const browser=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ctx=browser.contexts()[0],page=ctx.pages()[0];
page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(15000);
const fixture='https://mytree.joybeat.cn/__qa/native-files';
const handler=r=>r.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width,initial-scale=1"><h1>Emulator native file test</h1><button id="take">Camera</button><button id="choose">PDF</button><input hidden id="camera" type="file" accept="image/*" capture="environment"><input hidden id="document" type="file" accept="image/*,application/pdf"><p id="result">Waiting</p>'});
const report={mode:'actual-emulator-system-camera-and-DocumentsUI/synthetic-files',checks:[]};
const auto=process.argv.includes('--auto');
const nativeNodes=()=>{execFileSync(adb,['-s',serial,'shell','uiautomator','dump','/sdcard/hks-native-auto.xml']);return execFileSync(adb,['-s',serial,'shell','cat','/sdcard/hks-native-auto.xml'],{encoding:'utf8'});};
const pressNative=async(label,optional=false)=>{
 for(let attempt=0;attempt<(optional?1:12);attempt++){
  const xml=nativeNodes();
  for(const match of xml.matchAll(/<node[^>]+>/g)){
   const node=match[0];if(!node.includes('text="'+label+'"')&&!node.includes('content-desc="'+label+'"'))continue;
   const bounds=node.match(/bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);if(!bounds)continue;
   execFileSync(adb,['-s',serial,'shell','input','tap',String(Math.round((+bounds[1]+ +bounds[3])/2)),String(Math.round((+bounds[2]+ +bounds[4])/2))]);
   (report.nativeActions??=[]).push(label);return true;
  }
  await new Promise(r=>setTimeout(r,150));
 }
 if(!optional)throw Error('Native UI control missing: '+label);return false;
};

try{
 await ctx.route(fixture,handler);await page.goto(fixture);
 await page.evaluate(()=>{
  take.onclick=()=>camera.click();choose.onclick=()=>document.getElementById('document').click();
  for(const id of ['camera','document'])document.getElementById(id).onchange=async e=>{const f=e.target.files[0];if(!f)return;const bytes=await f.arrayBuffer();window['__'+id]={name:f.name,type:f.type,size:f.size,bytes:bytes.byteLength};if(id==='camera'){const image=new Image();image.src=URL.createObjectURL(f);await image.decode();window.__camera.width=image.naturalWidth;window.__camera.height=image.naturalHeight;}document.getElementById('result').textContent=JSON.stringify(window['__'+id]);};
 });
 await page.locator('#take').click();console.log('CAMERA_STARTED');if(auto){await pressNative('Shutter');await pressNative('Done');}
 await page.waitForFunction(()=>window.__camera?.width>0,{},{timeout:180000});
 report.camera=await page.evaluate(()=>window.__camera);report.checks.push('actual system camera writes grant-protected photo and returns readable image');
 console.log('CAMERA_RETURNED '+JSON.stringify(report.camera));
 await page.locator('#choose').click();console.log('DOCUMENTS_STARTED');if(auto&&!(await pressNative('hks-android-native.pdf',true))){await pressNative('Show roots');await pressNative('Downloads');await pressNative('hks-android-native.pdf');}
 await page.waitForFunction(()=>window.__document?.type==='application/pdf',{},{timeout:180000});
 report.pdf=await page.evaluate(()=>window.__document);report.checks.push('actual DocumentsUI returns readable PDF without storage permission');report.success=true;
}catch(e){report.failure=e.stack;process.exitCode=1;}
finally{
 fs.writeFileSync(path.resolve(import.meta.dirname,'../docs/evidence/android/native-files.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 await ctx.unroute(fixture,handler);await page.goto('https://mytree.joybeat.cn/',{waitUntil:'domcontentloaded',timeout:5000}).catch(()=>{});await Promise.race([browser.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);
}

process.exit(process.exitCode||0);
