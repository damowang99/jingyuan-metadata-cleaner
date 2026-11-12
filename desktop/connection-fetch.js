'use strict';
// Transport URL changes never change the logical account owner or request body.
const {accountOrigin}=require('./server-url');
const RETRY_SAFE=new Set(['/api/device/login','/api/events','/api/scanned-files','/api/file-records','/api/heartbeat']);
function createConnectionFetch({connection,fetcher}){return async function connectedFetch(input,options={}){
 const m=connection();if(!m)throw Error('连接检测尚未准备好');
 const url=new URL(input),managed=/^\/(api|downloads)\//.test(url.pathname)&&accountOrigin(url.origin)===m.logicalOrigin;
 if(!managed)throw Error('请求地址不属于当前已配对服务器，已阻止发送');
 const epoch=m.generation,origin=await m.guard(),method=(options.method||'GET').toUpperCase();
 const send=async base=>{if(epoch!==m.generation)throw Object.assign(Error('连接模式已变更，请重试'),{code:'SERVER_CHANGED'});const r=await fetcher(base+url.pathname+url.search,{...options,redirect:'error'});if(epoch!==m.generation)throw Object.assign(Error('连接模式已变更，请重试'),{code:'SERVER_CHANGED'});m.checkResponse(r);m.transportSuccess();return r;};
 try{return await send(origin);}catch(e){if(['SERVER_IDENTITY_MISMATCH','SERVER_OFFLINE','SERVER_CHANGED'].includes(e.code))throw e;if(m.current===origin)await m.transportFailure();
  if(m.current&&m.current!==origin&&(method==='GET'||RETRY_SAFE.has(url.pathname))){return await send(m.current);}throw e;
 }
};}
module.exports={createConnectionFetch};
