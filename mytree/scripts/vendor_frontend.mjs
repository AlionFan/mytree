import {cp,mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
const files={katex:['dist'],mathlive:['mathlive.min.js','mathlive-fonts.css','mathlive-static.css','fonts'],marked:['lib/marked.umd.js'],dompurify:['dist/purify.min.js']};
for(const [pkg,entries] of Object.entries(files)){
 const source=path.join(process.cwd(),'node_modules',pkg), target=path.join(process.cwd(),'web','vendor',pkg);await mkdir(target,{recursive:true});
 for(const entry of entries){const dest=entry==='dist'&&pkg==='katex'?target:path.join(target,path.basename(entry));await cp(path.join(source,entry),dest,{recursive:true});}
 const meta=JSON.parse(await readFile(path.join(source,'package.json'),'utf8'));await writeFile(path.join(target,'package-version.json'),JSON.stringify({name:pkg,version:meta.version,license:meta.license}));
 for(const file of ['LICENSE','LICENSE.txt','LICENSE.md']){try{await cp(path.join(source,file),path.join(target,file));}catch{}}
 console.log(pkg,meta.version);
}
