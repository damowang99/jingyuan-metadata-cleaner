const fs=require('node:fs/promises'),path=require('node:path');
const IMAGE_TYPES=new Set(['.jpg','.jpeg','.png','.webp','.gif','.bmp','.tif','.tiff','.heic','.heif','.avif']);
function filename(file){return String(file||'').split(/[\\/]/).pop()||'未命名文件';}
async function preview(file,nativeImage){
 if(!IMAGE_TYPES.has(path.extname(file).toLowerCase())||!nativeImage?.createThumbnailFromPath)return undefined;
 try{const stat=await fs.lstat(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>30*1024*1024)return;
 let image=await nativeImage.createThumbnailFromPath(file,{width:640,height:640});if(image.isEmpty())return;const size=image.getSize(),scale=Math.min(1,640/size.width,640/size.height);if(scale<1)image=image.resize({width:Math.max(1,Math.round(size.width*scale)),height:Math.max(1,Math.round(size.height*scale))});
 for(const quality of [60,40,25]){const jpeg=image.toJPEG(quality);if(jpeg.length&&jpeg.length<=90000)return jpeg.toString('base64');}
 }catch{} // An unsupported/missing image must never fail cleanup or count synchronization.
}
async function prepare(details,time,nativeImage){const items=[];for(const [ordinal,row] of (details||[]).entries()){
 if(typeof row.file!=='string')continue;const name=filename(row.file).slice(0,255);const error=String(row.error||'').replaceAll(row.file,name).slice(0,1000);
 items.push({ordinal,name,time,fields:Number(row.fields)||0,status:row.status==='仅检测'||row.sourceProcessed===false&&!error?'仅检测':error?'失败':'已清除',error,detected:(row.detected||[]).slice(0,100).map(x=>({tag:String(x.tag||'').slice(0,150),value:String(x.value||'').slice(0,1000)})),...(!error?{preview:await preview(row.file,nativeImage)}:{})});
 }return items;}
module.exports={prepare,preview,filename};
