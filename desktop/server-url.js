const {isIP}=require('node:net');
function isPrivateIPv4(host){if(isIP(host)!==4)return false;const [a,b]=host.split('.').map(Number);return a===10||(a===172&&b>=16&&b<=31)||(a===192&&b===168);}
// Example endpoints only. Replace both addresses before building a deployment.
const DEFAULT_SERVER='http://192.168.10.10:8787',PUBLIC_SERVER='http://203.0.113.10:8787',PUBLIC_HTTPS='https://203.0.113.10:8787';
function normalizeServer(value){
 if(typeof value!=='string'||!value.trim())throw Error('请输入服务地址');
 const input=value.trim(),hasScheme=/^[a-z][a-z0-9+.-]*:\/\//i.test(input);let url;
 try{url=new URL(hasScheme?input:'http://'+input);}catch{throw Error('服务地址格式不正确，请填写 IP:端口或完整网址');}
 if(url.username||url.password)throw Error('服务地址中不能包含账号密码');
 const local=['127.0.0.1','localhost','[::1]'].includes(url.hostname),privateHost=local||isPrivateIPv4(url.hostname);
 const approvedPublic=url.origin===PUBLIC_SERVER;
 if(!hasScheme&&!privateHost&&!approvedPublic)url.protocol='https:';
 if(url.protocol!=='https:'&&!(url.protocol==='http:'&&(privateHost||approvedPublic)))throw Error('公网服务器需使用HTTPS；HTTP仅支持本机、私有局域网或已授权的指定外网地址');
 return url;
}
function accountOrigin(server){const origin=normalizeServer(server).origin;return [PUBLIC_SERVER,PUBLIC_HTTPS].includes(origin)?DEFAULT_SERVER:origin;}
function ownerKey(session){return session?accountOrigin(session.server)+'|'+session.username:'';}
function selectUpdateServer(server,fallback=DEFAULT_SERVER){try{const origin=normalizeServer(server).origin;return [DEFAULT_SERVER,PUBLIC_SERVER,PUBLIC_HTTPS].includes(origin)?origin:fallback;}catch{return fallback;}}
module.exports={normalizeServer,isPrivateIPv4,DEFAULT_SERVER,PUBLIC_SERVER,accountOrigin,ownerKey,selectUpdateServer};
