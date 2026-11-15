'use strict';
(() => {
 const email=document.getElementById('email'),code=document.getElementById('code'),send=document.getElementById('send-code'),submit=document.getElementById('sign-in'),status=document.getElementById('login-status');
 let until=0,pending=false;
 // Only this fixed in-app destination is allowed; never navigate to arbitrary next values.
 const requested=new URLSearchParams(location.search).get('next');
 const destination=['/parent','/pricing'].includes(requested)?requested:'/';
 const returnQuery=destination==='/'?'':'?next='+encodeURIComponent(destination);
 document.querySelector('#auth-switch a').href='/signup'+returnQuery;
 const signup=location.pathname.replace(/\/$/,'')==='/signup';
 document.title=(signup?'注册':'登录')+' · 小树同学';
 document.getElementById('auth-heading').textContent=destination==='/parent'?(signup?'创建家庭学习账号':'登录学习账号'):(signup?'注册':'登录');
 if(destination==='/parent'){const note=document.createElement('p');note.className='intro';note.textContent='家长端与孩子端共用账号。已有学习记录，请使用孩子端原来的邮箱。';document.getElementById('auth-heading').after(note);}
 submit.textContent=signup?'注册 / 继续':'登录';
 if(signup){const switcher=document.getElementById('auth-switch');switcher.replaceChildren(document.createTextNode('已有账号？ '));const link=document.createElement('a');link.href='/login'+returnQuery;link.textContent='登录';switcher.append(link);}
 const message=(text,error=false)=>{status.textContent=text;status.classList.toggle('error',error);};
 const tick=()=>{const remaining=Math.max(0,Math.ceil((until-Date.now())/1000));send.disabled=pending||remaining>0;send.textContent=pending?'正在发送…':remaining?`${remaining} 秒后重发`:'获取验证码';};
 const post=async(path,body)=>{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(25000)});const data=await response.json();if(!response.ok)throw new Error(data.error||'暂时无法登录，请稍后重试。');return data;};
 send.addEventListener('click',async()=>{if(!email.reportValidity())return;pending=true;tick();message('正在发送验证码…');try{const result=await post('/api/auth/code',{email:email.value});until=Date.now()+result.retry_after*1000;message(result.message);code.focus();}catch(error){message(error instanceof TypeError?'网络连接失败，请检查网络后重试。':error.name==='TimeoutError'?'发送等待较久，请稍后重试。':error.message,true);}finally{pending=false;tick();}});
 document.getElementById('login-form').addEventListener('submit',async event=>{event.preventDefault();if(pending)return;submit.disabled=true;message('正在验证…');try{await post('/api/auth/verify',{email:email.value,code:code.value});location.replace(destination);}catch(error){message(error instanceof TypeError?'网络连接失败，请检查网络后重试。':error.name==='TimeoutError'?'验证等待较久，请稍后重试。':error.message,true);}finally{submit.disabled=false;}});
 setInterval(tick,1000);
})();
