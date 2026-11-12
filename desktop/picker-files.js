const fs=require('node:fs/promises'),path=require('node:path');
async function browse(input,{defaultPath,shortcuts=[]}={}){
 if(input!=null&&(typeof input!=='string'||input.length>32768))throw Error('路径格式无效');
 let directory=await fs.realpath(input||defaultPath),selected=null;
 const stat=await fs.stat(directory);if(stat.isFile()){selected=directory;directory=path.dirname(directory);}else if(!stat.isDirectory())throw Error('请选择普通文件或文件夹');
 const entries=(await fs.readdir(directory,{withFileTypes:true})).filter(e=>!e.isSymbolicLink()&&(e.isDirectory()||e.isFile())&&!e.name.startsWith('.cleaner-')).sort((a,b)=>Number(b.isDirectory())-Number(a.isDirectory())||a.name.localeCompare(b.name,'zh-CN',{numeric:true,sensitivity:'base'}));
 return {directory,parent:path.dirname(directory),selected,items:entries.slice(0,5000).map(e=>({name:e.name,path:path.join(directory,e.name),directory:e.isDirectory()})),truncated:entries.length>5000,shortcuts};
}
module.exports={browse};
