const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {promisify}=require('node:util'),execFile=promisify(require('node:child_process').execFile);
// Match any Adobe company/product string, not a fixed list of product names.
const {DEFAULT_KEYWORDS,isCleanupTarget}=require('./matcher');
const {removeVersionInfo}=require('./jpeg-provenance');
const supported=new Set(['.gif','.jpg','.jpeg','.tif','.tiff','.png','.webp','.psd','.psb','.pdf','.ai','.eps','.xmp','.dng','.heic','.heif','.avif','.jp2','.jxl','.svg','.indd','.ps']);
const images=new Set(['.gif','.jpg','.jpeg','.tif','.tiff','.png','.webp','.psd','.psb','.dng','.heic','.heif','.avif','.jp2','.jxl','.svg']);
const ignored=new Set(['errors','warnings','SourceFile','FileName','Directory','FileSize','FileModifyDate','FileAccessDate','FileInodeChangeDate','FilePermissions','FileType','FileTypeExtension','MIMEType','ExifToolVersion','Warning','Error']);
function targets(tags,{image=false,keywords=DEFAULT_KEYWORDS,sourceMode='keywords'}={}){return Object.entries(tags).filter(([k,v])=>!ignored.has(k.split(':').pop())&&isCleanupTarget(k,v,{image,keywords,sourceMode})).map(([k])=>k);}
function checkRead(tags){if(tags.Error||tags['ExifTool:Error'])throw Error(String(tags.Error||tags['ExifTool:Error']));}
async function copyMacXattrs(source,target){if(process.platform!=='darwin')return;const {stdout}=await execFile('/usr/bin/xattr',[source],{maxBuffer:1024*1024});for(const name of stdout.split('\n').filter(Boolean)){const value=await execFile('/usr/bin/xattr',['-px',name,source],{maxBuffer:32*1024*1024});await execFile('/usr/bin/xattr',['-wx',name,value.stdout.replace(/\s/g,''),target],{maxBuffer:1024*1024});}}
async function* walk(dir){for(const e of await fs.readdir(dir,{withFileTypes:true})){if(e.isSymbolicLink()||e.name.startsWith('.cleaner-'))continue;const p=path.join(dir,e.name);if(e.isDirectory())yield*walk(p);else if(e.isFile())yield p;}}
async function scan(root,tool,emit=()=>{},rewritePdf=null,policy={},onVisit=()=>{}){
 const entry=await fs.lstat(root);if(!entry.isDirectory()&&!entry.isFile())throw Error('请拖入普通文件或文件夹');
 const result={id:crypto.randomUUID(),fields:0,files:0,failed:0,scanned:0,skipped:0,inspect:policy.mode==='inspect'};Object.defineProperty(result,'skippedDetails',{value:[],enumerable:false});
 for await(const file of (entry.isFile()?[root]:walk(root))){
  result.scanned++;onVisit(file);const extension=path.extname(file).toLowerCase();if(!supported.has(extension)||(policy.extensions&&!policy.extensions.includes(extension))){result.skipped++;result.skippedDetails.push({file,reason:!supported.has(extension)?'格式暂不支持（'+(extension||'无扩展名')+'）':'当前清理策略不允许 '+extension+' 格式'});continue;}
  let temp,detected=[],isPdf=false;
  try{
   const image=images.has(extension),keywords=Array.isArray(policy.keywords)&&policy.keywords.length?policy.keywords:DEFAULT_KEYWORDS,sourceMode=policy.sourceMode==='keywords'?'keywords':'all';const before=await tool.read(file,['-G1','-a']);checkRead(before);const keys=targets(before,{image,keywords,sourceMode});if(!keys.length)continue;detected=keys.slice(0,16).map(tag=>({tag,value:String(typeof before[tag]==='string'?before[tag]:(JSON.stringify(before[tag])??before[tag])).slice(0,300)}));
   result.matched=(result.matched||0)+1;if(policy.mode==='inspect'){emit({file,status:'仅检测',fields:0,detected,sourceProcessed:false});continue;}
   isPdf=before['File:FileType']==='PDF'||path.extname(file).toLowerCase()==='.pdf';
   const stat=await fs.stat(file);if(stat.nlink>1)throw Error('跳过硬链接文件');
   temp=path.join(path.dirname(file),'.cleaner-'+crypto.randomUUID()+path.extname(file));await fs.copyFile(file,temp);
   if(isPdf){if(!rewritePdf)throw Error('PDF处理组件未安装');await rewritePdf(file,temp);}else await tool.write(temp,Object.fromEntries(keys.map(k=>[k,null])),['-overwrite_original']);
   let after=await tool.read(temp,['-G1','-a']);checkRead(after);let remaining=targets(after,{image,keywords,sourceMode});
   if(remaining.some(k=>k.startsWith('XMP-illustrator:'))){await tool.write(temp,{'XMP-illustrator:all':null},['-overwrite_original']);after=await tool.read(temp,['-G1','-a']);checkRead(after);remaining=targets(after,{image,keywords,sourceMode});}
   if(before['File:FileType']==='JPEG'&&remaining.some(k=>/^Photoshop:(WriterName|ReaderName)$/.test(k))){await removeVersionInfo(temp);after=await tool.read(temp,['-G1','-a']);checkRead(after);remaining=targets(after,{image,keywords,sourceMode});}
   if(remaining.length)throw Error('复核仍存在匹配字段：'+remaining.join('、'));
   const now=await fs.stat(file);if(now.size!==stat.size||now.mtimeMs!==stat.mtimeMs)throw Error('文件扫描期间发生变化');
   await copyMacXattrs(file,temp);await fs.utimes(temp,stat.atime,stat.mtime);await fs.chmod(temp,stat.mode);await fs.rename(temp,file);temp=null;
   result.fields+=keys.length;result.files++;emit({file,status:'已清除',fields:keys.length,detected,sourceProcessed:true});
  }catch(e){if(isPdf&&/已签名PDF不处理|加密PDF不处理/.test(e.message)){result.skipped++;result.skippedDetails.push({file,reason:e.message});emit({file,status:'跳过',error:e.message,detected,sourceProcessed:false});}else{result.failed++;emit({file,status:'失败',error:e.message,detected,sourceProcessed:false});}}
  finally{if(temp)await fs.unlink(temp).catch(()=>{});}
 }
 return result;
}
module.exports={targets,scan};
