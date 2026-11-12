const fs=require('node:fs/promises');
const {overlaps}=require('./folder-monitors');
async function prepareInputs(value,current=[]){
 const inputs=Array.isArray(value)?value:[value],directories=[],files=[];
 for(const input of inputs){
  if(typeof input!=='string'||!input)throw Error('请拖入文件或文件夹');
  const stat=await fs.lstat(input);
  if(!stat.isDirectory()&&!stat.isFile())throw Error('仅支持普通文件和文件夹，不支持快捷方式或符号链接');
  const resolved=await fs.realpath(input),list=stat.isDirectory()?directories:files;
  if(!list.includes(resolved))list.push(resolved);
 }
 const folders=current.map(f=>({...f}));
 for(const folder of directories){
  if(folders.some(f=>overlaps(f.path,folder)&&overlaps(folder,f.path)))continue;
  const parent=folders.find(f=>overlaps(f.path,folder)||overlaps(folder,f.path));
  if(parent)throw Error('文件夹与已添加的目录重叠：'+parent.path+'。子文件夹已包含在递归扫描中，请勿重复添加。');
  folders.push({path:folder,enabled:true});
 }
 return {directories,files:files.filter(file=>!directories.some(folder=>overlaps(folder,file))),folders};
}
module.exports={prepareInputs};
