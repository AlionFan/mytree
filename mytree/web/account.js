'use strict';
window.MytreeAccount=(async()=>{
 const originalFetch=window.fetch.bind(window);
 window.fetch=async(...args)=>{const response=await originalFetch(...args);if(response.status===401)location.replace('/login');return response;};
 try{
  const response=await fetch('/api/auth/me');if(!response.ok)return null;
  const {user}=await response.json();if(!user)return null;
  const container=document.querySelector('.header-inner');
  const menu=document.createElement('details');menu.className='account-menu';const summary=document.createElement('summary');summary.textContent='我';summary.setAttribute('aria-label','账号菜单');const panel=document.createElement('div');const label=document.createElement('p');label.textContent=user.email;panel.append(label);const member=document.createElement('a');member.href='/pricing';member.textContent='会员与额度';panel.append(member);const parent=document.createElement('a');parent.href='/parent';parent.textContent='家长入口';panel.append(parent);const button=document.createElement('button');button.textContent='退出登录';button.type='button';button.className='ghost small';panel.append(button);menu.append(summary,panel);container.append(menu);
  const memoryButton=document.createElement('button');memoryButton.type='button';memoryButton.className='ghost small';memoryButton.textContent='学习记忆';panel.insertBefore(memoryButton,button);
  memoryButton.onclick=async()=>{
   menu.open=false;const dialog=document.createElement('dialog');dialog.className='memory-dialog';
   const title=document.createElement('h2');title.textContent='学习记忆';const description=document.createElement('p');description.textContent='用于调整讲解和安排个性化复习，保留记录来源；不会改变成绩或知识点掌握状态。';
   const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>dialog.close();
   const list=document.createElement('div'),status=document.createElement('p');status.setAttribute('role','status');
   const post=async body=>{const r=await fetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'暂时无法读取记忆');return v;};
   const load=async()=>{const v=await post({action:'retrieve'});status.textContent=v.engine==='mem0'?'长期学习记忆已连接':(v.message||'当前使用来源记录');list.replaceChildren();if(!v.records.length)list.textContent='还没有记下讲解偏好。';for(const record of v.records){const row=document.createElement('article'),text=document.createElement('p'),source=document.createElement('small'),forget=document.createElement('button');let content=record.content;if(record.type==='fact'){try{const fact=JSON.parse(content);content=fact.event==='quiz_answer'?('练习记录：'+fact.knowledge+' · '+(fact.correct?'已答对':'还需巩固')+' · 提示层级 '+fact.max_hint_level):fact.event==='review'?('复习记录：'+(fact.completed?'已完成':'已保存')):'学过的题：'+fact.problem+(fact.note?' · 我的笔记：'+fact.note:'');}catch{content='一条已保存的学习记录';}}if(window.MathUI)text.innerHTML=window.MathUI.rich(content,true);else text.textContent=content;source.textContent='来源：'+(record.type==='preference'?'自己设置的讲解偏好':'自己的题卡')+' · 版本 '+record.version;forget.textContent='忘记这条';forget.onclick=async()=>{try{await post({action:'forget',memory_id:record.id});await load();}catch(e){status.textContent=e.message;}};row.append(text,source,forget);list.append(row);}};
   const styles=document.createElement('div');styles.className='memory-styles';for(const [value,label] of [['visual','多用图像'],['steps','分步讲解'],['examples','多举例子']]){const choice=document.createElement('button');choice.textContent=label;choice.onclick=async()=>{try{await post({action:'preference',style:value});await load();status.textContent='讲解偏好已更新';}catch(e){status.textContent=e.message;}};styles.append(choice);}
   dialog.append(title,description,styles,list,status,close);dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();try{await load();}catch(e){status.textContent=e.message;}
  };
  button.addEventListener('click',async()=>{button.disabled=true;try{const response=await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(response.ok)location.replace('/login');else throw new Error();}catch{button.textContent='退出失败，点击重试';button.disabled=false;}});
  return user;
 }catch{return null;}
})();
