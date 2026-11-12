const fs=require('node:fs/promises');
// Remove only the Photoshop VersionInfo image-resource block (0x0421).
// All other JPEG segments and the compressed image stream are copied verbatim.
function stripVersionInfo(input){
 if(input[0]!==255||input[1]!==216)throw Error('JPEG文件头无效');
 const chunks=[input.subarray(0,2)];let pos=2,removed=0;
 while(pos<input.length){const start=pos;if(input[pos++]!==255)throw Error('JPEG段结构无效');while(input[pos]===255)pos++;const marker=input[pos++];
  if(marker===0xda||marker===0xd9){chunks.push(input.subarray(start));return {data:Buffer.concat(chunks),removed};}
  if(marker===1||(marker>=0xd0&&marker<=0xd7)){chunks.push(input.subarray(start,pos));continue;}
  if(pos+2>input.length)throw Error('JPEG段长度无效');const length=input.readUInt16BE(pos),end=pos+length;if(length<2||end>input.length)throw Error('JPEG段长度无效');
  const payload=input.subarray(pos+2,end),signature=Buffer.from('Photoshop 3.0\0');
  if(marker===0xed&&payload.subarray(0,signature.length).equals(signature)){
   const kept=[signature];let at=signature.length,changed=false;
   while(at<payload.length){const first=at;if(at+7>payload.length||payload.toString('ascii',at,at+4)!=='8BIM')throw Error('Photoshop资源结构无效');const id=payload.readUInt16BE(at+4);at+=6;const nameLength=payload[at];at+=1+nameLength;if((1+nameLength)%2)at++;if(at+4>payload.length)throw Error('Photoshop资源长度无效');const size=payload.readUInt32BE(at);at+=4+size+(size%2);if(at>payload.length)throw Error('Photoshop资源长度无效');if(id===0x0421){changed=true;removed++;}else kept.push(payload.subarray(first,at));}
   if(changed){if(kept.length>1){const body=Buffer.concat(kept),header=Buffer.from([255,marker,0,0]);header.writeUInt16BE(body.length+2,2);chunks.push(header,body);}}else chunks.push(input.subarray(start,end));
  }else chunks.push(input.subarray(start,end));pos=end;
 }
 throw Error('JPEG图像数据缺失');
}
async function removeVersionInfo(file){const result=stripVersionInfo(await fs.readFile(file));if(result.removed)await fs.writeFile(file,result.data);return result.removed;}
module.exports={stripVersionInfo,removeVersionInfo};
