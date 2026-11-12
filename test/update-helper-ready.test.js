const {test}=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {waitForHelper}=require('../desktop/updater');
test('Windows app waits for matching helper token and PID before allowing exit',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'cleaner-ready-'));
 try{
  const child=Object.assign(new EventEmitter(),{pid:123,exitCode:null,signalCode:null}),config={ready:path.join(root,'ready.json'),token:'test-token',helperLog:path.join(root,'helper.log')};
  await fs.writeFile(config.ready,JSON.stringify({token:'wrong',pid:123}));let resolved=false;
  const waiting=waitForHelper(child,config,2000).then(()=>resolved=true);
  await new Promise(r=>setTimeout(r,120));assert.equal(resolved,false);
  await fs.writeFile(config.ready,JSON.stringify({token:config.token,pid:999}));await new Promise(r=>setTimeout(r,120));assert.equal(resolved,false);
  await fs.writeFile(config.ready,'\ufeff'+JSON.stringify({token:config.token,pid:123}));await waiting;assert.equal(resolved,true);assert.equal(child.listenerCount('exit'),0);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('helper failure or timeout returns an error instead of permitting client exit',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'cleaner-ready-error-'));
 try{
  const config={ready:path.join(root,'missing.json'),token:'test',helperLog:path.join(root,'helper.log')};
  const child=Object.assign(new EventEmitter(),{pid:123,exitCode:null,signalCode:null});const waiting=waitForHelper(child,config,2000);child.exitCode=1;child.emit('exit',1);await assert.rejects(waiting,/提前退出/);
  await assert.rejects(waitForHelper(Object.assign(new EventEmitter(),{pid:124,exitCode:null,signalCode:null}),config,120),/保留当前程序运行/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
