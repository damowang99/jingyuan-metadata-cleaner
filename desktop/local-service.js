const fs=require('node:fs/promises'),path=require('node:path');const {spawn}=require('node:child_process');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function startLocalService({resources,userData,port=8787}){
 const windows=process.platform==='win32';const runtime=path.join(resources,'bin',windows?'windows-python':'local-server');const executable=path.join(runtime,windows?'python.exe':'local-server');
 try{await fs.access(executable);}catch{throw Error('安装包缺少本机后台组件，请安装修正版客户端');}
 const url='http://127.0.0.1:'+port;
 const health=async()=>{try{const r=await fetch(url+'/api/health',{signal:AbortSignal.timeout(800)});const b=await r.json();return r.ok&&b.service==='metadata-cleaner';}catch{return false;}};
 // Never terminate a service owned by another running application.
 if(await health())return {url,external:true};
 let error='',exited=false;
 const child=spawn(executable,windows?[path.join(runtime,'local_server.py'),userData]:[userData],{env:{...process.env,CLEANER_LOCAL_PORT:String(port)},windowsHide:true,stdio:['ignore','ignore','pipe']});
 child.on('error',e=>{error=e.message;exited=true;});child.on('exit',()=>{exited=true;});child.stderr.on('data',b=>{error=(error+b.toString()).slice(-3000);});
 for(let i=0;i<120;i++){if(await health()){const credentials=JSON.parse(await fs.readFile(path.join(userData,'local-admin.json'),'utf8'));return {url,child,credentials};}if(exited)break;await sleep(100);}
 child.kill();throw Error('本机测试后台无法启动：'+(error||'启动超时，或8787端口已被占用'));
}
module.exports={startLocalService};
