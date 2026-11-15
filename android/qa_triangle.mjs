/* UI-only replay of saved real provider responses; no paid model calls here. */
import {createRequire} from 'node:module';import {spawn} from 'node:child_process';import readline from 'node:readline';import fs from 'node:fs';
const require=createRequire(import.meta.url),{chromium}=require('/Users/fan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');const svc=spawn('mytree/.venv/bin/python',['mytree/scripts/serve_qa_feedback.py']);const cfg=await new Promise(r=>readline.createInterface({input:svc.stdout}).once('line',l=>r(JSON.parse(l))));const b=await chromium.launch(),p=await b.newPage(),out='docs/evidence/feedback-1115';await p.addInitScript(()=>localStorage.setItem('mytree_demo','demo'));const report={checks:[],mode:'real provider diagram response replay into actual UI; fixture profile'},check=(n,v)=>{if(!v)throw Error(n);report.checks.push(n);};let family='domain';
try{
 await p.route('**/api/visual/lesson',async r=>{const body=r.request().postDataJSON(),v=JSON.parse(fs.readFileSync(`${out}/${family}-response.json`));await r.fulfill({json:{...v,diagnosis_id:body.diagnosis_id}});});
 for(const [width,height] of [[375,667],[390,844],[844,390]]){
  await p.setViewportSize({width,height});await p.goto(cfg.base);await p.waitForLoadState('networkidle');if(await p.locator('#usage-guide[open]').count())await p.locator('[data-close-guide]').first().click();await p.locator('[data-focus-switch=desk][data-value=cards]').click();
  for(family of ['triangle']){
   await p.locator('.stored-wrong:visible [data-diagram-lesson]').click();await p.locator('#diagram-lesson svg').waitFor();check(family+' actual graph '+width,await p.locator('#diagram-lesson svg :is(path,rect,polyline,circle)').count()>0);let i=1;
   for(;;){const next=p.locator('#diagram-lesson [data-diagram-step="1"]');await next.scrollIntoViewIfNeeded();check(family+' next reachable '+width+'/'+i,await next.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}));if(await next.isDisabled())break;await next.click();i++;}
   await p.screenshot({path:`${out}/${family}-ui-${width}.png`});await p.locator('[data-close-diagram]').click();
  }
 }report.success=true;
}catch(e){report.failure=e.stack;report.body=(await p.locator('body').innerText()).slice(0,1000);await p.screenshot({path:out+'/triangle-failure.png'});process.exitCode=1;}finally{fs.writeFileSync(`${out}/triangle-ui.json`,JSON.stringify(report,null,2));console.log({checks:report.checks.length,success:report.success,failure:report.failure});await b.close();svc.kill();}
