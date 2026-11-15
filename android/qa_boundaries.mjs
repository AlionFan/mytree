// Actual emulator WebView boundary tests. All test URLs are intercepted locally;
// no external attacker site is contacted and no personal profile is used.
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const adb='/Users/fan/Library/Android/sdk/platform-tools/adb',serial=process.env.ANDROID_SERIAL||'emulator-5554';
if(execFileSync(adb,['-s',serial,'shell','getprop','ro.kernel.qemu'],{encoding:'utf8'}).trim()!=='1')throw Error('Emulator required');
const browser=await chromium.connectOverCDP('http://127.0.0.1:9224',{noDefaults:true}),ctx=browser.contexts()[0],page=ctx.pages()[0];
page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(15000);
const origin='https://mytree.joybeat.cn',evil='https://blocked.invalid';
const policy="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'";
const report={mode:'actual-Android-WebView-emulator/locally-intercepted-boundaries',checks:[],externalRoutes:[]};
const check=(name,value)=>{if(!value)throw Error(name);report.checks.push(name);};
const trustedHandler=async route=>{
 const u=new URL(route.request().url());
 if(u.pathname==='/__qa/redirect')return route.fulfill({status:302,headers:{location:evil+'/marker'},body:''});
 if(u.pathname==='/__qa/resource-redirect')return route.fulfill({status:302,headers:{location:evil+'/script'},body:''});
 return route.fulfill({status:200,contentType:'text/html',headers:u.searchParams.has('csp')?{'Content-Security-Policy':policy}:{},body:'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trusted boundary fixture</title><h1>Trusted fixture</h1>'});
};
const evilHandler=async route=>{
 report.externalRoutes.push(route.request().url());
 if(route.request().url().endsWith('/script'))return route.fulfill({contentType:'application/javascript',body:'window.__badResource=true'});
 return route.fulfill({contentType:'text/html',body:'<title>UNTRUSTED_MARKER</title><h1>UNTRUSTED_MARKER</h1>'});
};
const ready=async(csp=false)=>{await page.goto(origin+'/__qa/fixture'+(csp?'?csp=1':''));await page.waitForFunction(()=>document.title==='Trusted boundary fixture');};
const settle=()=>page.waitForTimeout(400);
try{
 await ctx.route(origin+'/**',trustedHandler);await ctx.route(evil+'/**',evilHandler);
 await ready();await page.evaluate(url=>location.assign(url),evil+'/marker').catch(()=>{});await settle();
 check('programmatic foreign GET does not render marker',(await page.title())!=='UNTRUSTED_MARKER');
 await ready();await page.evaluate(url=>{const f=document.createElement('form');f.action=url;f.method='POST';document.body.append(f);f.submit();},evil+'/marker');await settle();
 check('foreign POST does not render marker',(await page.title())!=='UNTRUSTED_MARKER');
 await ready();await page.evaluate(()=>{const f=document.createElement('form');f.action='/__qa/redirect';f.method='POST';document.body.append(f);f.submit();});await settle();
 check('trusted top-level POST cannot redirect body to foreign origin',(await page.title())!=='UNTRUSTED_MARKER');
 await ready();await page.evaluate(url=>{const f=document.createElement('iframe');f.src=url;document.body.append(f);const s=document.createElement('script');s.src=url.replace('/marker','/script');document.body.append(s);},evil+'/marker');await settle();
 check('foreign subframe never renders marker',!(await Promise.all(page.frames().map(f=>f.title().catch(()=>'')))).includes('UNTRUSTED_MARKER'));
 check('foreign script never executes',await page.evaluate(()=>window.__badResource!==true));
 await ready();await page.evaluate(()=>location.assign('/__qa/redirect'));await settle();
 check('same-origin GET redirect cannot render foreign page',(await page.title())!=='UNTRUSTED_MARKER');
 await ready(true);await page.evaluate(()=>{const s=document.createElement('script');s.src='/__qa/resource-redirect';document.body.append(s);});await settle();
 check('production CSP blocks resource redirect to foreign origin',await page.evaluate(()=>window.__badResource!==true));
 await ready();await page.evaluate(()=>location.assign('http://mytree.joybeat.cn/__qa/plain'));await settle();
 check('HTTP navigation cannot render trusted fixture',!page.url().startsWith('http://mytree.joybeat.cn/'));
 check('no foreign request reached intercepted external route',report.externalRoutes.length===0);
 report.success=true;
}catch(e){report.failure=e.stack;process.exitCode=1;}
finally{
 await ctx.unroute(origin+'/**',trustedHandler);await ctx.unroute(evil+'/**',evilHandler);await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:5000}).catch(()=>{});
 execFileSync(adb,['-s',serial,'shell','uiautomator','dump','/sdcard/hks-boundary-check.xml']);
 const native=execFileSync(adb,['-s',serial,'shell','cat','/sdcard/hks-boundary-check.xml'],{encoding:'utf8'});
 report.nativeConfirmationLeft=native.includes('在浏览器中打开？');
 if(report.nativeConfirmationLeft){report.success=false;report.failure='Native external confirmation survived document navigation';process.exitCode=1;}
 else report.checks.push('document navigation dismisses native external confirmation');
 const out=path.resolve(import.meta.dirname,'../docs/evidence/android');fs.writeFileSync(path.join(out,'boundaries.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 await Promise.race([browser.close().catch(()=>{}),new Promise(r=>setTimeout(r,2000))]);
}
process.exit(process.exitCode||0);
