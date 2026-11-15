'use strict';
(() => {
 const escape = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const mf=window.MathfieldElement||window.MathLive?.MathfieldElement;
 if(mf){mf.fontsDirectory='/vendor/mathlive/fonts';mf.soundsDirectory=null;}
 const toLatex = s => {
  s=String(s??'');if(s.length>8000)throw Error('formula too long');s=s.replaceAll('²','^2').replaceAll('³','^3').replaceAll('−','-').replaceAll('≠',String.raw`\ne `).replaceAll('≤',String.raw`\le `).replaceAll('≥',String.raw`\ge `);
  if(s.includes('\\')||/[_^]\s*\{/.test(s))return s;
  return window.MathLive.convertAsciiMathToLatex(s);
 };
 const math = (source,display=false,ascii=false) => {
  try {const raw=String(source??'');const tex=ascii||(!raw.includes('\\')&&/[*/]/.test(raw))?toLatex(raw):raw;if(tex.length>8000)throw Error('formula too long');const shown=tex.replace(/_{3,}/g,String.raw`\underline{\qquad}`);return '<span class="native-math'+(display?' native-display':'')+'">'+katex.renderToString(shown,{displayMode:display,throwOnError:true,trust:false,strict:'ignore',maxExpand:500,maxSize:12,output:'mathml'})+'</span>';}
  catch{return '<span class="math-plain">'+escape(String(source??'').slice(0,8000))+'</span>';}
 };
 function rich(source,old=false){
  const tokens=[];
  const token=(value,display=false)=>{const id=tokens.length;tokens.push(math(value,display));return 'MATHRENDERTOKEN'+id+'END';};
  // Protect explicit math before Markdown or bare ASCII normalization.
  let text=String(source??'').replace(/\\\*/g,'*');
  text=text.replace(/\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\\\(([\s\S]*?)\\\)|(?<!\\)\$([^$\n]+)\$/g,(all,a,b,c,d)=>token(a??b??c??d,a!==undefined||b!==undefined));
  text=text.split(/(MATHRENDERTOKEN\d+END)/g).map(segment=>{
   if(/^MATHRENDERTOKEN\d+END$/.test(segment))return segment;
   return segment.replace(/[A-Za-z0-9α-ωπ∞()[\]{}_^+−\-*/=<>≠≤≥²³.×·÷\\]+(?:[ \t]+[A-Za-z0-9()[\]{}_^+−\-*/=<>≠≤≥²³.×·÷\\]+)*/g,part=>{
    if(!/[A-Za-z0-9]/.test(part))return part;
    if(!old&&!/[\^*/=×·÷]|\\(?:frac|sqrt)|[a-zA-Z]_\d/.test(part))return part;
    if(/^\*{1,2}[^*]+\*{1,2}$/.test(part.trim()))return part;
    if(!old&&/[a-zA-Z]{4,}/.test(part.replace(/\\(?:frac|sqrt|left|right|cdot|times)|sqrt|sin|cos|tan|log/g,'')))return part;
    return token(toLatex(part.trim()));
   });
  }).join('');
  const safe=DOMPurify.sanitize(marked.parse(text,{breaks:true,gfm:true}),{USE_PROFILES:{html:true},FORBID_TAGS:['img','style','iframe','form','input','math-field','button','textarea','select','option','dialog','details','summary','a'],FORBID_ATTR:['style'],ALLOW_DATA_ATTR:false});
  return safe.replace(/MATHRENDERTOKEN(\d+)END/g,(_,i)=>tokens[Number(i)]||'');
 }
 function field(value,attrs=''){
  const tex=toLatex(String(value??'').replace(/^\\\(([\s\S]*)\\\)$/,'$1').replace(/^\\\[([\s\S]*)\\\]$/,'$1'));
  return `<span class="formula-input"><math-field ${attrs} math-virtual-keyboard-policy="auto">${escape(tex)}</math-field><span class="formula-preview" aria-hidden="true">${tex?math(tex):'<span class="formula-placeholder">点击输入</span>'}</span></span>`;
 }
 function updatePreview(field){const preview=field.closest('.formula-input')?.querySelector('.formula-preview');if(preview)preview.innerHTML=field.value?math(field.value):'<span class="formula-placeholder">点击输入</span>';}
 document.addEventListener('input',event=>{if(event.target.tagName==='MATH-FIELD')updatePreview(event.target);});
 document.addEventListener('change',event=>{if(event.target.tagName==='MATH-FIELD')updatePreview(event.target);});
 document.addEventListener('focusout',event=>{if(event.target.tagName==='MATH-FIELD')updatePreview(event.target);});
 window.MathUI={math,rich,toLatex,field};
})();
