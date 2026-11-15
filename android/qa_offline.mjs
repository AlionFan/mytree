import {createRequire} from 'node:module';import {execFileSync} from 'node:child_process';import fs from 'node:fs';import path from 'node:path';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const adb='/Users/fan/Library/Android/sdk/platform-tools/adb',serial=process.env.ANDROID_SERIAL||'emulator-5554',origin='https://mytree.joybeat.cn';
const shell=(...args)=>execFileSync(adb,['-s',serial,'shell',...args],{encoding:'utf8'});
if(shell('getprop','ro.kernel.qemu').trim()!=='1')throw Error('Emulator required');
const b=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ctx=b.contexts()[0],page=ctx.pages()[0],client=await ctx.newCDPSession(page);page.setDefaultNavigationTimeout(10000);
const report={mode:'actual-emulator-WebView/network-offline/native-retry',checks:[]};
try{
 await client.send('Network.enable');await client.send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
 await page.goto(origin+'/login').catch(()=>{});
 shell('uiautomator','dump','/sdcard/hks-offline.xml');const xml=shell('cat','/sdcard/hks-offline.xml');
 if(!xml.includes('重新连接'))throw Error('native retry not visible');report.checks.push('offline main-frame load shows native retry');
 fs.writeFileSync(path.resolve(import.meta.dirname,'../docs/evidence/android/native/offline.png'),execFileSync(adb,['-s',serial,'exec-out','screencap','-p'],{maxBuffer:10e6}));
 await client.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
 const item=xml.match(/<node[^>]*text="重新连接"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);if(!item)throw Error('retry bounds missing');
 shell('input','tap',String(Math.round((+item[1]+ +item[3])/2)),String(Math.round((+item[2]+ +item[4])/2)));
 await page.waitForFunction(()=>document.title.includes('登录'),null,{timeout:10000});report.checks.push('native retry returns to real HTTPS login');report.success=true;
}catch(e){report.failure=e.stack;process.exitCode=1;}
finally{await client.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1}).catch(()=>{});fs.writeFileSync(path.resolve(import.meta.dirname,'../docs/evidence/android/offline.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));await Promise.race([b.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);}
process.exit(process.exitCode||0);
