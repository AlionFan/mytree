'use strict';
window.Explorer={mount({app,student,navigate}){
 if(!document.getElementById('explorer-voice-style')){const link=document.createElement('link');link.id='explorer-voice-style';link.rel='stylesheet';link.href='/explorer-voice.css';document.head.append(link);}
 const s={alive:true,active:false,mode:'observe',contexts:[],source:null,level:1,phase:'asleep',seq:0,running:false,stream:null,context:null,playback:null,resume:null,backup:null,pendingSpeech:null,requests:new Set(),timer:null,recorder:null,mic:null,recordIntent:false,recordCancel:false,recordTimer:null,micMonitor:null,lastDescription:'',history:[]};
 app.innerHTML=`<div class="page-intro"><h1>探索者</h1></div><div id="explorer-voice-layout" class="explorer-studio" data-mode="observe"><section class="panel explorer-camera-panel"><div id="explorer-camera-stage" class="camera-stage"><video id="explorer-video" autoplay muted playsinline aria-label="探索者摄像头预览"></video><div id="explorer-overlay"><svg viewBox="0 0 64 64" aria-hidden="true"><rect x="8" y="16" width="34" height="32" rx="8"/><path d="m42 26 14-8v28l-14-8Z"/></svg><strong>看画面，学英语</strong><span>点击“视频探索”，开启摄像头</span></div><div id="explorer-video-caption" class="camera-caption hidden" aria-hidden="true"></div><span id="explorer-indicator" class="camera-indicator">未开启摄像头</span></div><div id="explorer-mic-level" class="hidden"><label>麦克风音量 <meter id="explorer-mic-meter" min="0" max="1" value="0"></meter></label><span id="explorer-mic-message" role="status"></span></div><div id="explorer-state" role="status" aria-live="polite">选择一种探索方式</div><div class="explorer-mode-actions" role="group" aria-label="探索方式"><button id="explorer-voice-mode" class="ghost" aria-pressed="false">语音对话</button><button id="explorer-video-mode" aria-pressed="false">视频探索</button></div><p id="explorer-allowance" class="muted">仅预览不扣识图次数。<a href="/pricing">会员与额度</a></p></section><section class="panel explorer-conversation" aria-label="对话与字幕"><div class="transcript-heading"><h2>对话与字幕</h2><span id="explorer-language" class="source-tag">AI 语音</span></div><details class="voice-settings"><summary>围绕我的题目交流（可选）</summary><label>选择题目<select id="explorer-source"><option value="">自由对话（不选题）</option></select></label><label>讲解程度<select id="explorer-hint-level"><option value="1">先想一想</option><option value="2">关键一步</option><option value="3">完整讲解</option></select></label><details id="explorer-current-source"><summary>当前没有选题</summary><div id="explorer-source-detail"></div></details><p id="explorer-source-note" class="muted"></p></details><div id="explorer-caption" class="sr-only" aria-live="polite"></div><div id="explorer-history" class="explorer-history" role="log" aria-label="本次探索对话记录" tabindex="0"><p class="transcript-empty" data-transcript-empty>画面英语讲解、你的提问和 AI 回复会留在这里。公式也可以边听边看。</p></div><form id="explorer-question-form"><label for="explorer-question" class="sr-only">输入问题</label><textarea id="explorer-question" maxlength="300" placeholder="也可以输入文字，按 Enter 发送（Shift+Enter 换行）"></textarea><button id="explorer-send-question" hidden>发送</button></form></section><div hidden aria-hidden="true"><select id="explorer-mode"><option value="conversation">语音对话</option><option value="observe" selected>视频探索</option></select><button id="explorer-source-refresh">刷新题目</button><button id="explorer-toggle">继续</button><button id="explorer-camera-toggle">开启摄像头</button><button id="explorer-look">识别画面</button><button id="explorer-talk">语音提问</button><button id="explorer-cancel-recording" class="hidden">取消录音</button><button id="explorer-sleep">结束</button></div></div>`;
 let pendingObservation=null;
 async function refreshAllowance(value){try{if(!value&&window.MytreeAccount&&!(await window.MytreeAccount))return;if(!value){const r=await fetch('/api/billing/me');if(!r.ok)return;value=(await r.json()).explorer;}if(s.alive)$('explorer-allowance').firstChild.textContent=`本月剩余 ${value.remaining} / ${value.limit} 次 · 识图及带图提问每次计1次，预览不扣次数，纯语音不扣识图次数。`;}catch{}}
 async function observeImage(fields,token){const key=JSON.stringify(fields);if(!pendingObservation||pendingObservation.key!==key)pendingObservation={key,body:{...JSON.parse(JSON.stringify(fields)),image_data:frame(),request_id:crypto.randomUUID().replaceAll('-','')}};const result=await post('/api/explorer/observe',pendingObservation.body,token);pendingObservation=null;if(result.allowance)refreshAllowance(result.allowance);return result;}
 const $=id=>document.getElementById(id),video=$('explorer-video');
 function caption(text){$('explorer-caption').textContent=text;$('explorer-language').textContent=/[\u3400-\u9fff]/.test(text)?'AI 语音 · 中文':'AI 语音 · English';$('explorer-video-caption').textContent=text;}
 refreshAllowance();
 let phaseTimer=null;
 function phase(value,message){if(!s.alive)return;clearInterval(phaseTimer);s.phase=value;$('explorer-state').textContent=message;if(['observing','answering','transcribing','audio'].includes(value)){const started=performance.now();phaseTimer=setInterval(()=>{if(s.alive)$('explorer-state').textContent=message+' · '+Math.floor((performance.now()-started)/1000)+'秒';},1000);}renderControls();}
 function renderControls(){
  if(!s.alive)return;const awake=s.active||!!s.stream,paused=s.phase==='paused';
  $('explorer-toggle').textContent=!awake?'开始语音对话':paused?(pendingObservation?'重试这次识图':s.resume||s.pendingSpeech?'继续播报':'继续对话'):'打断播报';
  $('explorer-camera-toggle').textContent=s.phase==='opening'?'取消开启摄像头':s.stream?'关闭摄像头':'开启摄像头';$('explorer-look').disabled=!s.stream||s.phase==='opening';$('explorer-camera-stage').classList.remove('hidden');$('explorer-voice-layout').dataset.mode=s.mode;$('explorer-voice-mode').setAttribute('aria-pressed',String(s.mode==='conversation'&&s.active));$('explorer-video-mode').setAttribute('aria-pressed',String(s.mode==='observe'&&!!s.stream));
  $('explorer-talk').disabled=!awake||s.phase==='opening';$('explorer-talk').textContent=s.recordIntent?'结束并提问':'语音提问';
  $('explorer-sleep').disabled=!awake&&s.phase!=='opening';$('explorer-cancel-recording').classList.toggle('hidden',!s.recordIntent);
  $('explorer-question').disabled=false;$('explorer-question').maxLength=s.mode==='observe'?800:300;$('explorer-send-question').disabled=false;
  $('explorer-overlay').classList.toggle('hidden',!!s.stream);
  $('explorer-indicator').textContent=({asleep:'休息中',opening:'等待摄像头',observing:'正在看',speaking:s.mode==='observe'?'英语播报':'语音播报',paused:'已打断',recording:'正在录音',microphone:'等待麦克风',transcribing:'正在听懂',answering:'正在想',audio:'准备朗读'})[s.phase]||s.phase;
 }
 function invalidate(){s.seq++;for(const controller of s.requests)controller.abort();s.requests.clear();clearTimeout(s.timer);s.timer=null;}
 async function post(path,body,token=s.seq){
  const controller=new AbortController();s.requests.add(controller);const timeout=setTimeout(()=>controller.abort(),90000);
  try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student,...body}),signal:controller.signal});const data=await response.json().catch(()=>{throw new Error('暂时没有收到回复，请稍后重试；也可以输入文字提问。');});if(!response.ok)throw new Error(typeof data.error==='object'?data.error.message:data.error||'暂时没有连上，请重试。');if(!s.alive||token!==s.seq)throw new DOMException('Cancelled','AbortError');return data;}
  catch(error){if(error.name==='AbortError'&&token===s.seq)throw new Error('等待较久，可以按继续再试。');if(error instanceof TypeError)throw new Error('网络暂时没有连上，请检查网络后重试；也可以输入文字提问。');throw error;}
  finally{clearTimeout(timeout);s.requests.delete(controller);}
 }
 async function audioContext(){const Constructor=window.AudioContext||window.webkitAudioContext;if(!Constructor)throw new Error('当前浏览器无法播放语音，请换用较新的浏览器。');if(!s.context||s.context.state==='closed')s.context=new Constructor();if(s.context.state==='suspended')await s.context.resume();return s.context;}
 function freezePlayback(){
  const playing=s.playback;
  if(playing){playing.offset=Math.min(playing.buffer.duration,playing.offset+Math.max(0,s.context.currentTime-playing.startedAt));playing.source.onended=null;playing.source.stop();s.playback=null;s.resume={...playing,source:null};}
  else if(s.pendingSpeech)s.resume={...s.pendingSpeech};
  s.pendingSpeech=null;
 }
 function cancelObservation(){if(pendingObservation){const request_id=pendingObservation.body.request_id;pendingObservation=null;fetch('/api/explorer/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id}),keepalive:true}).catch(()=>{});}}
 function pause(message='已打断。可以继续播报，或按键问一句。'){
  if(!s.active&&!s.stream)return;cancelObservation();invalidate();s.running=false;freezePlayback();
  if(s.recordIntent)stopRecording(true);
  if(!s.resume&&s.backup){s.resume=s.backup;s.backup=null;}
  phase('paused',message);
 }
 function fail(error,token){if(!s.alive||token!==s.seq||error.name==='AbortError')return;s.running=false;phase(s.active||s.stream?'paused':'asleep',error.message||'暂时无法完成，可以重试。');}
 async function waitForCameraPixels(token){
  const started=performance.now(),canvas=document.createElement('canvas');canvas.width=48;canvas.height=32;const ctx=canvas.getContext('2d',{willReadFrequently:true});
  let decoded=0,cancelFrame=null;
  if(video.requestVideoFrameCallback){const seen=()=>{decoded++;if(s.alive&&token===s.seq)cancelFrame=video.requestVideoFrameCallback(seen);};cancelFrame=video.requestVideoFrameCallback(seen);}
  try{while(s.alive&&token===s.seq){
   if(video.readyState>=2&&video.videoWidth&&video.videoHeight){
    ctx.drawImage(video,0,0,48,32);const pixels=ctx.getImageData(0,0,48,32).data;let lit=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]+pixels[i+1]+pixels[i+2]>18)lit++;
    if(lit>8&&(decoded>0||video.currentTime>0.03))return;
    // A genuinely dark scene still has decoded frames; do not wait forever for brightness.
    if(performance.now()-started>3500&&(decoded>=2||video.currentTime>0.2))return;
   }
   if(performance.now()-started>7000)throw Error('摄像头还没有送来有效画面，请结束后重新唤醒。');
   await new Promise(resolve=>setTimeout(resolve,80));
  }}finally{if(cancelFrame!==null&&video.cancelVideoFrameCallback)video.cancelVideoFrameCallback(cancelFrame);}
 }
 function frame(){
  if(!s.stream||video.readyState<2||!video.videoWidth)throw new Error('摄像头画面还没准备好，请稍后按继续。');
  const canvas=document.createElement('canvas'),scale=Math.min(1,768/video.videoWidth);canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);return canvas.toDataURL('image/jpeg',.65);
 }
 function schedule(){s.running=false;phase('paused','本次英语探索已完成。再次点击“视频探索”关闭摄像头，下次开启时识别新画面。');}
 function finishSpeech(kind){s.playback=null;if(!s.alive)return;if(kind==='question'){s.running=false;if(s.backup){s.resume=s.backup;s.backup=null;}phase('paused','回答已播完。可以继续原来的播报，或再问一句。');}else if(s.running){schedule();}else phase('paused','已暂停，可以按继续。');}
 function playBuffer(item,token){
  if(token!==s.seq||!s.alive)return;
  if(item.offset>=item.buffer.duration-.02){finishSpeech(item.kind);return;}
  const source=s.context.createBufferSource();source.buffer=item.buffer;source.connect(s.context.destination);item={...item,source,startedAt:s.context.currentTime};s.playback=item;s.pendingSpeech=null;
  source.onended=()=>{if(s.alive&&token===s.seq&&s.playback?.source===source)finishSpeech(item.kind);};
  const language=/[\u3400-\u9fff]/.test(item.text)?'中文':'英语';phase('speaking','正在用'+language+(item.kind==='question'?'回答':'播报')+'，随时可以打断。');source.start(0,item.offset);
 }
 const speechCache=new Map();
 async function speak(text,kind,token){
  if(speechCache.has(text)){playBuffer({text,kind,offset:0,buffer:speechCache.get(text)},token);return;}
  s.pendingSpeech={text,kind,offset:0};phase('audio','回复已准备好，正在生成语音…');
  let result;
  try{result=await post('/api/speech',{action:'speak',text},token);}
  catch(error){if(error.name==='AbortError'||token!==s.seq)throw error;throw new Error('语音暂时无法播放，回复文字已保留。可以重新选择探索方式重试。');}
  const bytes=Uint8Array.from(atob(result.audio_data.split(',')[1]),c=>c.charCodeAt(0));
  const buffer=await s.context.decodeAudioData(bytes.buffer);if(token!==s.seq||!s.alive)return;
  speechCache.set(text,buffer);if(speechCache.size>6)speechCache.delete(speechCache.keys().next().value);
  playBuffer({text,kind,offset:0,buffer},token);
 }
 async function observe(){
  if(!s.running||!s.alive)return;const token=s.seq;phase('observing','正在看当前画面…');
  try{const result=await observeImage({previous_description:''},token);
   if(result.changed){s.lastDescription=result.description;addTurn('assistant',result.description);caption(result.description);await speak(result.description,'narration',token);}else{phase('observing','画面没有明显变化，继续看看…');schedule();}
  }catch(error){fail(error,token);}
 }
 async function wake(){
  if(s.active||s.stream)pause('正在开启摄像头…');
  invalidate();const token=s.seq;s.lastDescription='';s.resume=null;s.backup=null;phase('opening','请允许摄像头权限。尚未开启麦克风。');
  try{
   await audioContext();
   if(!s.alive||token!==s.seq)return;
   if(!navigator.mediaDevices?.getUserMedia)throw new Error('摄像头需要 HTTPS 和浏览器支持，请在系统浏览器中打开。');
   const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});
   if(!s.alive||token!==s.seq){stream.getTracks().forEach(track=>track.stop());return;}
   s.stream=stream;s.active=true;video.srcObject=stream;for(const track of stream.getVideoTracks())track.addEventListener('ended',()=>{if(s.stream===stream)closeCamera();},{once:true});
   await video.play();
   await waitForCameraPixels(token);
   if(!s.alive||token!==s.seq)return;s.mode='observe';$('explorer-mode').value='observe';s.running=true;phase('observing','正在看画面学英语…');await observe();
  }catch(error){if(token!==s.seq)return;if(s.stream){s.stream.getTracks().forEach(track=>track.stop());s.stream=null;}fail(new Error(error.name==='NotAllowedError'?'摄像头未获允许，仍可开始语音对话。需要看画面时，再在浏览器设置允许摄像头。':error.message),token);}
 }
 async function resume(){
  if(!s.active&&!s.stream){await startVoice();return;}if(pendingObservation){await retryObservation();return;}if(s.recordIntent){stopRecording(false);return;}
  invalidate();const token=s.seq;try{await audioContext();if(!s.alive||token!==s.seq)return;s.running=true;const item=s.resume||s.pendingSpeech||s.backup;s.resume=null;s.pendingSpeech=null;if(item===s.backup)s.backup=null;
   if(item?.buffer)playBuffer(item,token);else if(item?.text)await speak(item.text,item.kind,token);else if(s.mode==='observe'&&s.stream)observe();else phase('paused','可以点击语音提问，或在文字框输入问题。');
  }catch(error){fail(error,token);}
 }
 function appendTranscript(node){
  const log=$('explorer-history'),follow=log.scrollHeight-log.clientHeight-log.scrollTop<56;
  log.querySelector('[data-transcript-empty]')?.remove();log.append(node);
  if(follow)log.scrollTop=log.scrollHeight;
 }
 function addTurn(role,text){
  s.history.push({role,content:text});s.history=s.history.slice(-6);
  const node=document.createElement('article');node.className='explorer-turn '+role;
  const tag=document.createElement('span');tag.className='source-tag';tag.textContent=role==='user'?'我的提问':s.mode==='observe'?'AI · 画面英语':'AI · 题目与语音辅导';
  const content=document.createElement('div');content.className='math-prose';if(window.MathUI)content.innerHTML=MathUI.rich(text);else content.textContent=text;
  node.append(tag,content);appendTranscript(node);
 }
 async function ask(question){
  question=question.trim();if(!question)return;
  if(!s.active)s.active=true;
  if(s.mode==='observe'&&!s.stream){phase('paused','看画面学英语需要先开启摄像头；也可以切回语音对话。');return;}
  if(s.mode==='observe'&&pendingObservation?.body.question===question){await retryObservation();return;}
  pause();const token=s.seq,priorHistory=s.history.slice();addTurn('user',question);
  if(s.resume&&s.resume.kind==='narration')s.backup=s.resume;s.resume=null;
  phase('answering',s.mode==='observe'?'正在结合当前画面回答…':'正在听懂你的问题，准备简短讲解…');
  try{
   await audioContext();if(!s.alive||token!==s.seq)return;
   const result=s.mode==='observe'?await observeImage({question,history:priorHistory},token):await post('/api/explorer/conversation',{question,history:priorHistory,source_id:s.source?.source_id||'',source_revision:s.source?.source_revision||'',level:s.level},token);
   const reply=result.reply||result.description;addTurn('assistant',reply);caption(reply);await audioContext();if(!s.alive||token!==s.seq)return;await speak(result.speech_text||reply,'question',token);
  }catch(error){fail(error,token);}
 }

 async function retryObservation(){
  const pending=pendingObservation;if(!pending||!s.stream)return;
  invalidate();const token=s.seq,question=pending.body.question,kind=question?'question':'narration';s.running=!question;
  phase(question?'answering':'observing','正在重试原图与原问题…');
  try{const result=await post('/api/explorer/observe',pending.body,token);if(pendingObservation!==pending)return;pendingObservation=null;if(result.allowance)refreshAllowance(result.allowance);
   if(question)addTurn('assistant',result.description);else {s.lastDescription=result.description;if(result.changed)addTurn('assistant',result.description);}
   if(result.changed){caption(result.description);await audioContext();if(!s.alive||token!==s.seq)return;await speak(result.description,kind,token);}else schedule();
  }catch(error){fail(error,token);}
 }
 function monitorMic(stream){
  const source=s.context.createMediaStreamSource(stream),analyser=s.context.createAnalyser();analyser.fftSize=1024;source.connect(analyser);const samples=new Float32Array(analyser.fftSize);$('explorer-mic-level').classList.remove('hidden');
  const interval=setInterval(()=>{if(!s.alive||s.mic!==stream)return;analyser.getFloatTimeDomainData(samples);let energy=0;for(const v of samples)energy+=v*v;const rms=Math.sqrt(energy/samples.length);$('explorer-mic-meter').value=Math.min(1,rms*12);const message=rms>.002?'检测到声音，请说完一句话再结束。':'暂未检测到声音，请检查麦克风是否静音或选错设备。';if($('explorer-mic-message').textContent!==message)$('explorer-mic-message').textContent=message;},200);
  const stop=()=>{clearInterval(interval);source.disconnect();analyser.disconnect();if(s.micMonitor===stop){s.micMonitor=null;$('explorer-mic-level').classList.add('hidden');}};s.micMonitor=stop;return stop;
 }
 function stopMic(){s.micMonitor?.();clearTimeout(s.recordTimer);s.recordTimer=null;if(s.mic){s.mic.getTracks().forEach(track=>track.stop());s.mic=null;}}
 async function voiceWav(blob){
  // Normalize browser WebM/MP4 containers to a small, consistent PCM WAV upload.
  if(!blob.size)throw new Error('这次没有录到声音，请重新点语音提问，确认音量有变化后说话。');
  let buffer;try{buffer=await s.context.decodeAudioData(await blob.arrayBuffer());}catch{throw new Error('这次录音没有保存完整，请重新录制；也可以输入文字提问。');}
  if(buffer.duration<.35)throw new Error('录音太短，请点“语音提问”，说完一句话后再点“结束并提问”。');
  if(buffer.duration>21)throw new Error('录音较长，请每次说一句话，控制在20秒以内。');
  const count=Math.ceil(buffer.duration*16000),bytes=new ArrayBuffer(44+count*2),view=new DataView(bytes);
  const text=(offset,value)=>[...value].forEach((c,i)=>view.setUint8(offset+i,c.charCodeAt(0)));
  text(0,'RIFF');view.setUint32(4,36+count*2,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,count*2,true);
  const channels=Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i));
  let energy=0,peak=0;
  for(let i=0;i<count;i++){const index=Math.min(buffer.length-1,Math.floor(i*buffer.sampleRate/16000));const sample=Math.max(-1,Math.min(1,channels.reduce((sum,ch)=>sum+ch[index],0)/channels.length));energy+=sample*sample;peak=Math.max(peak,Math.abs(sample));view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true);}
  if(peak<.003&&Math.sqrt(energy/count)<.0006)throw new Error('没有检测到麦克风声音。请检查麦克风是否静音、选对输入设备后重录；也可以输入文字提问。');
  return new Blob([bytes],{type:'audio/wav'});
 }
 function stopRecording(cancel){
  s.recordIntent=false;s.recordCancel=cancel;clearTimeout(s.recordTimer);
  if(s.recorder?.state==='recording')s.recorder.stop();else{stopMic();if(s.active||s.stream)phase('paused','录音已取消，可以继续播报。');}
 }
 async function record(){
  if((!s.active&&!s.stream)||s.recordIntent)return;pause();const token=s.seq;s.recordIntent=true;s.recordCancel=false;phase('microphone','请允许麦克风权限；只在这次按键说话时录音。');
  try{
   if(!window.MediaRecorder)throw new Error('当前浏览器不支持录音，可以先在右侧输入问题。');
   await audioContext();if(!s.alive||token!==s.seq||!s.recordIntent)return;
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
   if(!s.alive||token!==s.seq||!s.recordIntent){stream.getTracks().forEach(track=>track.stop());return;}
   s.mic=stream;const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type));const recorder=new MediaRecorder(stream,mime?{mimeType:mime}:{});s.recorder=recorder;const chunks=[];let size=0,recordFailure='';const stopMeter=monitorMic(stream);
   recorder.ondataavailable=event=>{if(event.data.size){chunks.push(event.data);size+=event.data.size;if(size>2000000){recordFailure='录音较长，请每次说一句话，控制在20秒以内。';stopRecording(true);}}};
   recorder.onerror=()=>{recordFailure='录音中断了，请检查麦克风是否被其他应用占用，再重新录制；也可以输入文字提问。';stopRecording(true);phase('paused',recordFailure);};
   recorder.onstop=async()=>{
    stopMeter();stream.getTracks().forEach(track=>track.stop());if(s.mic===stream)s.mic=null;
    if(s.recorder===recorder){s.recorder=null;clearTimeout(s.recordTimer);s.recordTimer=null;}
    if(!s.alive||token!==s.seq||s.recordCancel){if(s.alive&&(s.active||s.stream)&&token===s.seq)phase('paused',recordFailure||'录音已取消，可以继续播报。');return;}
    phase('transcribing','正在识别你刚才说的话…');
    try{const wav=await voiceWav(new Blob(chunks,{type:recorder.mimeType||mime}));if(!s.alive||token!==s.seq)return;const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(wav);});if(!s.alive||token!==s.seq)return;const result=await post('/api/speech',{action:'transcribe',audio_data:data},token);$('explorer-question').value=result.text;await ask(result.text);}catch(error){fail(error,token);}
   };
   recorder.start(250);phase('recording','正在录音。松开 V，或点“结束并提问”。');s.recordTimer=setTimeout(()=>stopRecording(false),20000);
  }catch(error){s.recordIntent=false;stopMic();const messages={NotAllowedError:'麦克风权限未开启，请在浏览器地址栏允许麦克风后重试；也可以输入文字提问。',NotFoundError:'没有找到麦克风，请连接麦克风或在系统设置选择输入设备；也可以输入文字提问。',NotReadableError:'麦克风暂时无法使用，请关闭其他占用麦克风的应用后重试；也可以输入文字提问。'};fail(new Error(messages[error.name]||'录音没有开始，请检查麦克风权限后重试；也可以输入文字提问。'),token);}
 }
 function sleep(message='探索已结束，摄像头和麦克风都已关闭。'){
  cancelObservation();
  invalidate();s.active=false;s.running=false;freezePlayback();s.resume=null;s.backup=null;if(s.recordIntent||s.recorder)stopRecording(true);stopMic();
  const stream=s.stream;s.stream=null;if(stream)stream.getTracks().forEach(track=>track.stop());video.srcObject=null;$('explorer-video-caption').classList.add('hidden');
  if(s.context){s.context.close().catch(()=>{});s.context=null;}phase('asleep',message);
 }
 function clearConversation(message){
  if(s.active||s.stream)pause(message);else invalidate();s.history=[];s.resume=null;s.pendingSpeech=null;s.backup=null;speechCache.clear();$('explorer-question').value='';if($('explorer-history').querySelector('.explorer-turn')){const note=document.createElement('p');note.className='transcript-context';note.textContent=message||'已切换探索方式';appendTranscript(note);}
  if(s.active||s.stream)phase('paused',message);
 }
 function showSource(){
  const source=s.source;const summary=$('explorer-current-source').querySelector('summary');summary.textContent=source?source.title+' · 当前题目':'当前没有选题';
  const detail=$('explorer-source-detail');detail.replaceChildren();if(source){if(window.MathUI)detail.innerHTML=MathUI.rich(source.problem);else detail.textContent=source.problem;const label=document.createElement('p');label.textContent=source.verification?.label||'题目来源已保存；AI讲解需核对';detail.append(label);const facts=document.createElement('p');facts.textContent=source.kind==='practice'?(source.verification?.level!=='verified'?'参考练习，未作成绩判定':'已保存尝试 '+source.facts.attempts+' 次；'+(source.facts.correct?'已答对':'尚无答对记录')):source.kind==='quiz'?(source.facts.submitted?'已提交过答案':'尚未提交答案'):'以保存的原题与原样作答为依据';detail.append(facts);}
  $('explorer-source-note').textContent=source?.kind==='quiz'?'检验题的实际辅导会记录提示使用；完整讲解会影响独立完成条件。':source?'本次只围绕这道本人题目辅导，AI讲解不作为新的判题结果。':'可直接语音或文字交流；要讨论上传题或练习，请先选题。';
 }
 async function loadSources(){
  try{const r=await fetch('/api/explorer/contexts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student})});if(!s.alive)return;if(!r.ok)throw Error();const result=await r.json();const selected=s.source?.source_id;s.contexts=result.items;const select=$('explorer-source');select.replaceChildren(new Option('自由对话（不选题）',''));for(const row of s.contexts)select.add(new Option(row.title+' · '+row.problem.replace(/\\[()[\]]|\$/g,'').slice(0,48),row.source_id));s.source=s.contexts.find(row=>row.source_id===selected)||null;select.value=s.source?.source_id||'';showSource();}catch{if(s.alive)$('explorer-source-note').textContent='题目列表暂时没有加载好，可刷新重试；仍可自由对话。';}
 }
 async function startVoice(){s.active=true;s.mode='conversation';$('explorer-mode').value='conversation';phase('paused','语音对话已开始，再点一次结束录音并提问。');await record();}
 function closeCamera(){
  clearConversation('摄像头已关闭，可以继续语音对话。');const stream=s.stream;s.stream=null;if(stream)stream.getTracks().forEach(track=>track.stop());video.srcObject=null;s.lastDescription='';s.mode='conversation';$('explorer-mode').value='conversation';s.active=true;phase('paused','摄像头已关闭，可以继续语音对话。');
 }
 function toggle(){if(!s.active&&!s.stream)startVoice();else if(s.recordIntent)stopRecording(false);else if(s.phase==='paused')resume();else pause();}
 const toggleButton=$('explorer-toggle'),talk=$('explorer-talk'),sleepButton=$('explorer-sleep'),cancel=$('explorer-cancel-recording'),form=$('explorer-question-form');
 $('explorer-voice-mode').onclick=()=>{if(s.mode!=='conversation'||!s.active){sleep();clearConversation('');startVoice();}else if(s.recordIntent)stopRecording(false);else if(['speaking','answering','transcribing','audio','microphone'].includes(s.phase))pause('已打断，再点语音对话继续提问。');else record();};
 $('explorer-video-mode').onclick=()=>{if(s.stream||s.phase==='opening'){sleep();return;}sleep();clearConversation('');s.source=null;$('explorer-source').value='';s.mode='observe';$('explorer-mode').value='observe';showSource();wake();};
 $('explorer-question').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();ask(event.target.value);}};
 toggleButton.onclick=toggle;talk.onclick=()=>s.recordIntent?stopRecording(false):record();sleepButton.onclick=()=>sleep();cancel.onclick=()=>stopRecording(true);form.onsubmit=event=>{event.preventDefault();ask($('explorer-question').value);};
 $('explorer-camera-toggle').onclick=()=>s.stream||s.phase==='opening'?closeCamera():wake();
 $('explorer-look').onclick=()=>{clearConversation('正在识别当前画面…');s.source=null;$('explorer-source').value='';showSource();s.mode='observe';$('explorer-mode').value='observe';s.running=true;observe();};
 $('explorer-mode').onchange=event=>{clearConversation('对话方式已更换，可以重新提问。');s.mode=event.target.value;if(s.mode==='observe'){s.source=null;$('explorer-source').value='';showSource();}renderControls();};
 $('explorer-source').onchange=event=>{if(s.stream||s.phase==='opening')sleep('已切换到题目辅导，摄像头已关闭。');clearConversation('题目已更换，可以围绕当前题目重新提问。');s.source=s.contexts.find(row=>row.source_id===event.target.value)||null;s.mode='conversation';$('explorer-mode').value='conversation';showSource();renderControls();};
 $('explorer-hint-level').onchange=event=>{clearConversation('辅导程度已更换，请重新提问。');s.level=Number(event.target.value);};$('explorer-source-refresh').onclick=()=>{clearConversation('正在刷新题目，请重新提问。');loadSources();};loadSources();renderControls();
 function keydown(event){if(document.querySelector('dialog[open]'))return;if(event.repeat||event.altKey||event.ctrlKey||event.metaKey||event.target.closest('textarea,input,select,math-field'))return;if(event.code==='Space'){event.preventDefault();if(s.mode==='observe'&&!s.stream)$('explorer-video-mode').click();else toggle();}if(event.code==='KeyV'&&(s.active||s.stream)){event.preventDefault();record();}if(event.code==='Escape'&&(s.active||s.stream)){event.preventDefault();sleep();}}
 function keyup(event){if(document.querySelector('dialog[open]'))return;if(event.code==='KeyV'&&s.recordIntent){event.preventDefault();stopRecording(false);}}
 function visibility(){if(document.hidden)sleep('已暂停');}
 document.addEventListener('keydown',keydown);document.addEventListener('keyup',keyup);document.addEventListener('visibilitychange',visibility);
 return {destroy(){sleep();s.alive=false;clearInterval(phaseTimer);speechCache.clear();document.removeEventListener('keydown',keydown);document.removeEventListener('keyup',keyup);document.removeEventListener('visibilitychange',visibility);}};
}};
