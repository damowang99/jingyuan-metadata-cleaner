const crypto=require('node:crypto'),os=require('node:os');
const {accountOrigin}=require('./server-url'),{accountFolders,overlaps}=require('./folder-monitors');
async function loadIdentity({read,save,safeStorage,user=()=>os.userInfo().username,computer=()=>os.hostname()}){
 const username=String(user()).trim().slice(0,80),hostname=String(computer()||'本机').slice(0,120);if(!username)throw Error('无法读取当前系统用户名');
 let saved=await read('device-identity',{}),identity;
 try{identity=saved.encrypted?JSON.parse(safeStorage.decryptString(Buffer.from(saved.encrypted,'base64'))):saved;}catch{identity={};}
 if(!/^[a-f0-9-]{36}$/.test(identity?.id||'')||!/^[a-f0-9]{64}$/.test(identity?.secret||''))identity={id:crypto.randomUUID(),secret:crypto.randomBytes(32).toString('hex')};
 identity={...identity,osUsername:username,hostname};
 const data=safeStorage.isEncryptionAvailable()?{encrypted:safeStorage.encryptString(JSON.stringify(identity)).toString('base64')}:identity;await save('device-identity',data);return identity;
}
function deviceSession(identity,server,token=''){return {server,username:'device-'+identity.id,name:identity.osUsername,computer:identity.hostname,device:true,token};}
function migrateLocal(settings,history,pending,target){
 const dest=accountOrigin(target.server)+'|'+target.username;const sourceOwners=new Set();
 const belongs=owner=>{if(owner===dest)return true;const pos=owner.lastIndexOf('|');if(pos<0)return false;try{return accountOrigin(owner.slice(0,pos))===accountOrigin(target.server)||/^http:\/\/(127\.0\.0\.1|localhost):8787$/.test(owner.slice(0,pos));}catch{return false;}};
 for(const owner of [...Object.keys(settings.accounts||{}),...history.map(r=>r.owner||''),...pending.map(r=>r.owner||'')])if(belongs(owner)&&owner!==dest)sourceOwners.add(owner);
 const existing=settings.accounts[dest]||{},folders=accountFolders(existing),scanTimes={...existing.scanTimes};
 for(const owner of sourceOwners){const meta=settings.accounts[owner]||{};for(const f of accountFolders(meta))if(!folders.some(a=>overlaps(a.path,f.path)||overlaps(f.path,a.path)))folders.push(f);for(const [dir,time]of Object.entries(meta.scanTimes||{}))if(!scanTimes[dir]||time>scanTimes[dir])scanTimes[dir]=time;}
 settings.accounts[dest]={...existing,folders,scanTimes};
 const seen=new Map(),merged=[];for(const record of history){const r=sourceOwners.has(record.owner)?{...record,legacyOwner:record.legacyOwner||record.owner,owner:dest}:record;const id=r.owner+'|'+r.id;if(seen.has(id)){if(r.cleared)Object.assign(seen.get(id),r);continue;}seen.set(id,r);merged.push(r);}
 const queue=new Map();for(const record of pending){const r=sourceOwners.has(record.owner)?{...record,owner:dest}:record;queue.set(r.owner+'|'+r.data.id,r);}
 return {history:merged,pending:[...queue.values()]};
}
module.exports={loadIdentity,deviceSession,migrateLocal};
