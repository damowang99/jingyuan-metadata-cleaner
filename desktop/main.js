const ScanInventory=require('./scan-inventory');const FileRecords=require('./file-records');const DeviceNetwork=require('./device-network');
const {loginItemSettings,updateToken,isBackgroundUpdate,shouldShowWindow,presentWindow}=require('./startup-visibility');
const {app,BrowserWindow,ipcMain,dialog,Tray,Menu,nativeImage,safeStorage,shell,nativeTheme,net:electronNet}=require('electron');
Menu.setApplicationMenu(null);nativeTheme.themeSource='dark';
const {ExifTool}=require('exiftool-vendored');const {migrateAccount}=require('./central-account');const {dailySummary}=require('./ui');const {ReleaseUpdater,verifyManifest}=require('./updater');const updateConfig=require('./update-config.json');const {scan}=require('./scanner');const {DEFAULT_KEYWORDS}=require('./matcher');const {FolderMonitors,accountFolders,overlaps}=require('./folder-monitors');const {normalizeServer,accountOrigin,ownerKey,selectUpdateServer}=require('./server-url');const ScanResults=require('./scan-results');const {clearLocalDetails,localTotals}=require('./history-records');const ContextClean=require('./context-clean');const {completionMessage}=require('./scan-completion');const {loadIdentity,deviceSession,migrateLocal}=require('./device-identity');
const fs=require('node:fs/promises'),path=require('node:path');const {createClientFetch}=require('./client-network');const rawClientFetch=createClientFetch({fetcher:(url,options)=>process.platform==='darwin'?electronNet.fetch(url,{...options,bypassCustomProtocolHandlers:true}):fetch(url,options),version:()=>app.getVersion(),transport:process.platform==='darwin'?'chromium':'node',report:async detail=>{const folder=app.getPath('userData');await fs.mkdir(folder,{recursive:true});await fs.appendFile(path.join(folder,'network-events.log'),JSON.stringify(detail)+'\n',{mode:0o600});}});const {promisify}=require('node:util');const execFileAsync=promisify(require('node:child_process').execFile);
const {ServerConnection,LAN,WAN}=require('./server-connection');const {createConnectionFetch}=require('./connection-fetch');
let connectionManager=null,connectionTimer=null,recovering=null,lastConnectedRevision=0;const routedFetch=createConnectionFetch({connection:()=>connectionManager,fetcher:rawClientFetch});const clientFetch=(url,options)=>connectionManager?routedFetch(url,options):rawClientFetch(url,options);
function logLifecycle(event,detail={}){try{const folder=app.getPath('userData'),nativeFs=require('node:fs');nativeFs.mkdirSync(folder,{recursive:true});nativeFs.appendFileSync(path.join(folder,'startup-events.log'),JSON.stringify({time:new Date().toISOString(),version:app.getVersion(),pid:process.pid,event,...detail})+'\n',{mode:0o600});}catch{}}
process.on('uncaughtExceptionMonitor',error=>logLifecycle('uncaught-exception',{error:error.stack||error.message}));
logLifecycle('process-start',{updateLaunch:!!updateToken(process.argv),hidden:process.argv.includes('--hidden')});
let win,tray,session=null,busy=false,quitting=false,installPending=false,installing=false,syncing=false,releaseUpdater=null,updateText='每10分钟自动检查更新',updateDetails='',settings={autoStart:true,accounts:{}},pending=[],history=[],filePending=[],syncState='idle',syncError='',nextSyncAt=0,syncRetryIndex=0;
let webJob=null,webController=null,externalBusy=false;
let choosingInputs=false;let manualBatch=null;let backgroundStartup=isBackgroundUpdate({argv:process.argv,platform:process.platform});
let localService=null,serviceStartup=null,deviceIdentity=null,deviceLoginTask=null;
async function ensureLocalService(){if(localService?.child&&(localService.child.exitCode!==null||localService.child.signalCode!==null))localService=null;if(localService)return localService;if(!serviceStartup)serviceStartup=require('./local-service').startLocalService({resources:process.resourcesPath,userData:app.getPath('userData')}).then(s=>{localService=s;notify();return s;}).finally(()=>{serviceStartup=null;});return serviceStartup;}
const launchAck=process.argv.find(a=>a.startsWith('--update-ack='));if(launchAck&&/^[a-f0-9]{32}$/.test(launchAck.slice(13))){fs.mkdir(app.getPath('userData'),{recursive:true}).then(()=>fs.writeFile(path.join(app.getPath('userData'),'update-start-'+launchAck.slice(13)+'.json'),JSON.stringify({pid:process.pid,token:launchAck.slice(13)}),{mode:0o600})).catch(()=>{});}
const tool=new ExifTool();const file=n=>path.join(app.getPath('userData'),n+'.json');
async function read(n,fallback){try{return JSON.parse(await fs.readFile(file(n),'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
let writes=Promise.resolve();function save(n,data){const body=JSON.stringify(data);writes=writes.catch(()=>{}).then(async()=>{await fs.writeFile(file(n)+'.tmp',body,{mode:0o600});await fs.rename(file(n)+'.tmp',file(n));});return writes;}
function key(){return ownerKey(session);}
function account(){return settings.accounts[key()]||{};}
function send(channel,data){if(win&&!win.isDestroyed())win.webContents.send(channel,data);}
function state(){return {connection:connectionManager?.snapshot()||null,syncStatus:connectionManager?.phase==='offline'||connectionManager?.phase==='identity-mismatch'?'offline':syncing?'syncing':syncState==='failed'?'failed':pending.some(e=>e.owner===key())||filePending.some(e=>e.owner===key())?'pending':'synced',syncError,platform:process.platform,nameConfirmed:!!settings.deviceNameConfirmed,policy:settings.fleetPolicy||{mode:"adobe",watch:true,keywords:DEFAULT_KEYWORDS},contextStatus:settings.contextStatus||"尚未安装",failedTasks:Object.values(account().failedTasks||{}),webJob:webJob?.owner===key()?webJob:null,user:session?{name:session.name,username:session.username,computer:session.computer||'',device:!!session.device,server:session.server}:null,busy:busy||externalBusy||!!webJob?.running||installing||!!manualBatch,scanSummary:account().scanSummary||null,localStats:localTotals(history,key()),folders:accountFolders(account()).map(f=>({...f,lastScanAt:account().scanTimes?.[f.path]||null,...monitor.status(f.path),...(manualBatch?.remaining.has(f.path)?{scanning:manualBatch.currentRoot===f.path,queued:manualBatch.currentRoot!==f.path}:{})})),autoStart:settings.autoStart,packaged:app.isPackaged,version:app.getVersion(),translocated:process.execPath.includes('/AppTranslocation/'),configuredServer:settings.manualServer||settings.server||updateConfig.server,update:updateText,updateDetails,localBackend:!!localService,pending:pending.filter(e=>e.owner===key()).length+filePending.filter(e=>e.owner===key()).length,summary:dailySummary(history.filter(e=>e.owner===key())),history:history.filter(e=>e.owner===key()&&!e.cleared).slice(-100).reverse()};}
function makeTrayIcon(){const assets=require('./tray-icon.json');const png=process.platform==='darwin'?assets.dark:((nativeTheme.shouldUseDarkColorsForSystemIntegratedUI??nativeTheme.shouldUseDarkColors)?assets.light:assets.dark);const full=nativeImage.createFromDataURL('data:image/png;base64,'+png),size=process.platform==='darwin'?18:20,image=full.resize({width:size,height:size});if(image.addRepresentation)image.addRepresentation({scaleFactor:2,buffer:full.resize({width:size*2,height:size*2}).toPNG()});image.setTemplateImage(process.platform==='darwin');return image;}
function notify(){send('state',state());}
// The connection manager only changes transport aliases. accountOrigin/ownerKey remain unchanged.
function initConnection(){
 const stored=normalizeServer(settings.server||updateConfig.server).origin;
 const mode=settings.connectionMode|| (accountOrigin(stored)===LAN?'auto':'manual');
 settings.connectionMode=mode;settings.manualServer=settings.manualServer||stored;
 connectionManager=new ServerConnection({fetcher:rawClientFetch,mode,manual:settings.manualServer,pairings:settings.serverPairings||{},options:settings.connectionOptions||{},persist:async pins=>{settings.serverPairings=pins;await save('settings',settings);},onChange:s=>{
  if(s.current&&session&&accountOrigin(session.server)===s.logicalOrigin){session.server=s.current;settings.server=s.current;if(releaseUpdater)releaseUpdater.server=selectUpdateServer(s.current,updateConfig.server);save('settings',settings).catch(e=>logLifecycle('connection-save-failed',{message:e.message}));}
  notify();
  if(s.status==='online'&&s.revision!==lastConnectedRevision){lastConnectedRevision=s.revision;nextSyncAt=0;}
  if(s.status==='online')Promise.resolve().then(()=>recoverConnection().catch(e=>logLifecycle('connection-recovery-failed',{message:e.message})));
 }});return connectionManager;
}
async function recoverConnection(){
 if(recovering||!connectionManager?.current||!session?.device)return;
 const task=(async()=>{if(!session.token||session.syncedName!==session.name)await authenticateDevice();await heartbeat();await sync();})();recovering=task;try{await task;}finally{if(recovering===task)recovering=null;}
}
async function changeConnection(mode,server){
 if(busy||externalBusy||webJob?.running||installing||manualBatch||choosingInputs)throw Error('请等待当前任务结束');
 const target=mode==='auto'?LAN:normalizeServer(server).origin,previous=key();
 if(!connectionManager)initConnection();
 // Pause detection while switching a genuinely different logical account. Aliases retain all state.
 if(accountOrigin(session?.server||target)!==accountOrigin(target)){connectionManager.generation++;connectionManager.current='';connectionManager.phase='checking';monitor.stop();await useDevice(target);await resume();}
 settings.connectionMode=mode;if(mode==='manual')settings.manualServer=target;await save('settings',settings);
 await connectionManager.setMode(mode,settings.manualServer||target);nextSyncAt=0;if(previous!==key())notify();
 return {ok:connectionManager.phase==='online',message:connectionManager.error||'已连接服务器',state:state()};
}
ipcMain.handle('connection-mode',(_,mode)=>changeConnection(mode,settings.manualServer||LAN));
ipcMain.handle('connection-recheck',async()=>{if(!connectionManager)initConnection();await connectionManager.check({force:true});nextSyncAt=0;await recoverConnection();return state();});
ipcMain.handle('connection-pair',async()=>{
 const m=connectionManager,c=m?.candidate;if(!c)throw Error('请先检测服务器');
 const {response}=await dialog.showMessageBox(win,{type:'question',title:'确认公司服务器',message:'请与管理员核对服务器身份',detail:c.origin+'\n服务器 ID：'+c.id+'\n确认后将连接并同步本机记录。HTTP 身份 ID 仅用于防止误连，不能替代 HTTPS。',buttons:['取消','确认并连接'],defaultId:0,cancelId:0});
 if(response===1){await m.confirmPair(c);await recoverConnection();}return state();
});
async function authenticateDevice(){
 if(!session?.device||!deviceIdentity)return;
 const ctx=session,owner=key();if(deviceLoginTask?.ctx===ctx)return deviceLoginTask.promise;
 const promise=(async()=>{const r=await clientFetch(ctx.server+'/api/device/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({deviceId:deviceIdentity.id,deviceSecret:deviceIdentity.secret,osUsername:settings.deviceDisplayName||deviceIdentity.osUsername,computer:deviceIdentity.hostname}),signal:AbortSignal.timeout(15000)});let body;try{body=await r.json();}catch{throw Error('账号服务返回无效响应，请检查服务地址');}if(!r.ok){const error=Error(body.error||'电脑身份同步失败（HTTP '+r.status+'）');error.status=r.status;throw error;}if(!body.token||body.username!==ctx.username)throw Error('服务器尚未支持此客户端的电脑身份识别，请更新后端');if(session===ctx){session.token=body.token;session.syncedName=body.name;notify();}return body;})();deviceLoginTask={owner,ctx,promise};try{return await promise;}finally{if(deviceLoginTask?.promise===promise)deviceLoginTask=null;}
}
async function useDevice(server){
 if(!deviceIdentity)deviceIdentity=await loadIdentity({read,save,safeStorage});
 const previous=session,next=deviceSession(deviceIdentity,server);if(previous?.device&&ownerKey(previous)===ownerKey(next))next.token=previous.token;
 next.name=settings.deviceDisplayName||next.name;if(previous&&accountOrigin(previous.server)!==accountOrigin(server))delete settings.fleetPolicy;session=next;settings.server=server;({history,pending}=migrateLocal(settings,history,pending,next));await save('settings',settings);await save('history',history);await save('pending',pending);notify();
}
async function request(route,data,ctx=session){if(!ctx)throw Error('电脑身份尚未准备好');if(ctx.device&&!ctx.token){await authenticateDevice();if(ownerKey(ctx)!==key())throw Error('服务器已切换');ctx.token=session.token;}let r;try{r=await clientFetch(ctx.server+route,{method:data?'POST':'GET',headers:{'Content-Type':'application/json',Authorization:'Bearer '+(ctx.token||'')},...(data?{body:JSON.stringify(data)}:{}),signal:AbortSignal.timeout(15000)});}catch(e){throw e;}let b;try{b=await r.json();}catch(e){throw Error('账号服务返回了无法解析的响应（HTTP '+r.status+'），请检查服务器地址或代理设置');}if(r.status===401&&ctx.device&&ownerKey(ctx)===key()&&!ctx.renewing){ctx.token='';ctx.renewing=true;try{await authenticateDevice();if(ownerKey(ctx)!==key())throw Error('服务器已切换');ctx.token=session.token;return await request(route,data,ctx);}finally{ctx.renewing=false;}}if(!r.ok){const error=Error(b.error||'请求失败');error.status=r.status;throw error;}return b;}
async function remember(){if(safeStorage.isEncryptionAvailable())await save('session',{encrypted:safeStorage.encryptString(JSON.stringify(session)).toString('base64')});else send('notice','系统安全存储不可用，下次启动需重新登录');}
async function queueFileDetails(owner,event,details,time){if(!details?.length||filePending.some(e=>e.owner===owner&&e.event===event))return;const items=await FileRecords.prepare(details,time,nativeImage);if(items.length){filePending.push({owner,event,items,cursor:0});await save('pending-files',filePending);}}
async function sync(){
 if(syncing||!session||Date.now()<nextSyncAt)return;
 syncing=true;syncState='syncing';syncError='';notify();const ctx={...session},owner=ownerKey(ctx);
 try{
  if(session.device&&session.syncedName!==session.name)await authenticateDevice();
  if(owner!==key())return;ctx.token=session.token;
  for(const e of [...pending]){
   if(e.owner!==owner)continue;
   const ack=await request('/api/events',e.data,ctx);
   if(ack.accepted!==true||ack.event_id!==e.data.id)throw Error('服务端未确认接收清理记录');
   if(Array.isArray(e.scanIdentities)){
    let cursor=e.inventoryCursor||0;
    do{const files=e.scanIdentities.slice(cursor,cursor+500);
     const response=await request('/api/scanned-files',{event:e.data.id,files,final:cursor+500>=e.scanIdentities.length},ctx);
     if(response.accepted!==true)throw Error('服务端未确认接收扫描明细');
     cursor+=500;e.inventoryCursor=cursor;await save('pending',pending);
    }while(cursor<e.scanIdentities.length);
   }
   const next=pending.filter(x=>x!==e);await save('pending',next);pending=pending.filter(x=>x!==e);if(pending.length!==next.length)await save('pending',pending);notify();
  }
  const record=settings.accounts[owner]||(settings.accounts[owner]={});
  if(!record.fileDetailsBackfilled){for(const row of history.filter(r=>r.owner===owner&&!r.cleared&&r.id&&r.details?.length)){await queueFileDetails(owner,row.id,row.details,row.time);if(owner!==key())return;}record.fileDetailsBackfilled=true;await save('settings',settings);}
  for(const e of [...filePending]){
   if(e.owner!==owner)continue;
   while((e.cursor||0)<e.items.length){if(owner!==key())return;const start=e.cursor||0,response=await request('/api/file-records',{event:e.event,items:e.items.slice(start,start+10)},ctx);
    if(response.accepted!==true)throw Error('服务端未确认接收文件明细');
    e.cursor=start+10;await save('pending-files',filePending);
   }
   const next=filePending.filter(x=>x!==e);await save('pending-files',next);filePending=filePending.filter(x=>x!==e);if(filePending.length!==next.length)await save('pending-files',filePending);notify();
  }
  syncState='idle';syncRetryIndex=0;nextSyncAt=0;syncError='';
 }catch(e){syncState='failed';syncError=e.message;const delays=connectionManager?.options.offlineRetryMs||[15000,30000,60000,120000,300000];const delay=[400,401,403,409,422].includes(e.status)?300000:delays[Math.min(syncRetryIndex++,delays.length-1)];nextSyncAt=Date.now()+delay;throw e;}
 finally{syncing=false;notify();}
}

async function rewritePdf(src,dst){const resources=app.isPackaged?process.resourcesPath:__dirname;const python=path.join(resources,'bin','windows-python','python.exe');if(process.platform==='win32'){try{await fs.access(python);await fs.unlink(dst);await execFileAsync(python,[path.join(resources,'bin','windows-python','pdf_clean.py'),src,dst],{timeout:120000,maxBuffer:1024*1024,windowsHide:true});return;}catch(e){if(e.code!=='ENOENT')throw e;}}const binary=path.join(app.isPackaged?process.resourcesPath:__dirname,'bin','pdf-clean','pdf-clean'+(process.platform==='win32'?'.exe':''));await fs.unlink(dst);await execFileAsync(binary,[src,dst],{timeout:120000,maxBuffer:1024*1024});}
const monitor=new FolderMonitors({run:performScan,onChange:notify,onWarning:text=>{send('notice',text);notify();},onError:e=>{send('notice','监听或扫描失败：'+e.message);notify();}});
async function recordScan(folder,reason,result){
 const owner=key(),meta=settings.accounts[owner]||{},time=new Date().toISOString();
 if(result&&reason!=='单文件清理')meta.scanTimes={...meta.scanTimes,[folder]:time};
 if(manualBatch?.owner===owner&&manualBatch.remaining.has(folder)){
  if(result)ScanResults.add(manualBatch.totals,result);else manualBatch.failedRoots++;
  manualBatch.remaining.delete(folder);
  if(!manualBatch.remaining.size){meta.scanSummary={mode:'manual',roots:manualBatch.roots,time,totals:manualBatch.totals,failedRoots:manualBatch.failedRoots};manualBatch=null;}
 }else if(result&&reason!=='单文件清理'&&(!meta.scanSummary||meta.scanSummary.mode==='background'))meta.scanSummary={mode:'background',roots:1,time,totals:result};
 settings.accounts[owner]=meta;await save('settings',settings);
}
async function showCompletion(result,message=completionMessage(result)){
 let report;
 if(result?.skippedDetails?.length){try{const directory=path.join(app.getPath('userData'),'scan-reports');await fs.mkdir(directory,{recursive:true});report=path.join(directory,'skipped-'+require('node:crypto').randomUUID()+'.txt');await fs.writeFile(report,'\ufeff跳过文件清单\n'+new Date().toISOString()+'\n\n'+result.skippedDetails.map((r,i)=>(i+1)+'. '+r.file+'\n原因：'+r.reason).join('\n\n'),{encoding:'utf8',mode:0o600,flag:'wx'});message.buttons=['查看跳过清单','知道了'];message.defaultId=1;message.cancelId=1;}catch(e){send('notice','跳过清单未保存：'+e.message);}}
 const answer=await dialog.showMessageBox(win,message);if(report&&answer.response===0){const error=await shell.openPath(report);if(error)send('notice','无法打开跳过清单：'+error);}
}
async function firstScanNotice(owner,folder,result,error){const meta=settings.accounts[owner];if(owner!==key()||!meta?.firstScanNotices?.[folder])return;delete meta.firstScanNotices[folder];await save('settings',settings);const message=completionMessage(result||{failed:1,scanned:0});message.title='文件夹扫描结果';message.message=error?'首次扫描未完成':'首次扫描已完成';message.detail=folder+'\n\n'+(error?'扫描失败：'+error.message:message.detail);await showCompletion(result,message);}
async function performScan(folder,reason){if(!session||installing)return;busy=true;notify();const owner=key(),details=[],identities=new Set(),started=Date.now(),policy=settings.fleetPolicy||{};settings.accounts[owner]||={};try{const result=await scan(folder,tool,e=>{details.push(e);const tasks=settings.accounts[owner].failedTasks||(settings.accounts[owner].failedTasks={});if(e.error)tasks[e.file]={file:e.file,error:e.error,time:new Date().toISOString()};else if(e.sourceProcessed)delete tasks[e.file];send('progress',e);},rewritePdf,policy,file=>identities.add(ScanInventory.identity(file)));result.durationMs=Date.now()-started;result.reason=policy.mode==='inspect'?reason+'（仅检测）':reason;result.policyRevision=policy.revision||0;if(result.skipped&&settings.accounts[owner].failedTasks?.[folder])settings.accounts[owner].failedTasks[folder].error='当前策略不允许该文件类型，已跳过';if(!result.failed&&!result.skipped&&policy.mode!=='inspect')delete settings.accounts[owner].failedTasks?.[folder];await recordScan(folder,reason,result);if(result.files||result.failed||reason!=='文件夹变动'){history.push({owner,folder,reason,time:new Date().toISOString(),...result,details});history=history.slice(-1000);await save('history',history);}await queueFileDetails(owner,result.id,details,new Date().toISOString());if(result.scanned||result.fields||result.failed){pending.push({owner,data:result,scanIdentities:[...identities]});await save('pending',pending);}await firstScanNotice(owner,folder,result);sync().catch(e=>send('notice','统计待同步：'+e.message));return result;}catch(error){await recordScan(folder,reason,null);await firstScanNotice(owner,folder,null,error);throw error;}finally{if(reason!=='单文件清理'){busy=false;notify();if(installPending)await startPendingUpdate();}}}
async function resume(){monitor.restore(settings.fleetPolicy?.watch===false?[]:accountFolders(account()));notify();}
function show(){presentWindow(win,app,{platform:process.platform,afterUpdate:!!updateToken(process.argv)});logLifecycle('window-presented',{visible:win.isVisible(),focused:win.isFocused()});notify();}
async function confirmUpdateStartup(){const token=updateToken(process.argv);if(!token)return;await new Promise(resolve=>setTimeout(resolve,3000));const quiet=isBackgroundUpdate({argv:process.argv,platform:process.platform});if(!win||win.isDestroyed()||!tray||tray.isDestroyed?.()||win.webContents.isCrashed?.())throw Error('Updated application is not ready');if(!quiet){show();if(!win.isVisible())throw Error('Updated application window did not become visible');}const acknowledgement={token,version:app.getVersion(),pid:process.pid,visible:win.isVisible(),ready:true,trayReady:true,background:quiet};logLifecycle('update-startup-confirmed',acknowledgement);await fs.writeFile(path.join(app.getPath('userData'),'update-ack-'+token+'.json'),JSON.stringify(acknowledgement),{mode:0o600});backgroundStartup=false;}
function updateStatus(text,details=''){updateText=text;updateDetails=details;notify();}
async function startPendingUpdate(){if(busy||externalBusy||externalQueue.length||webJob?.running||manualBatch||choosingInputs||installing||!releaseUpdater?.pending)return;installing=true;monitor.stop();notify();try{await writes;updateStatus('已验证更新包，正在准备自动安装…');await releaseUpdater.launchInstall({resources:process.resourcesPath,executable:process.execPath});quitting=true;app.quit();}catch(e){installing=false;installPending=false;if(releaseUpdater)releaseUpdater.pending=null;updateStatus('自动安装未完成，当前版本仍可使用',e.message);if(session)await resume();}}
async function checkUpdate(){if(!app.isPackaged){updateStatus('开发模式，未启用自动安装');return;}if(releaseUpdater?.pending)return startPendingUpdate();if(releaseUpdater){try{const current=await connectionManager?.guard();if(current&&accountOrigin(current)!==LAN)throw Error('手动服务器不属于公司更新源，请切回自动模式检查公司更新');releaseUpdater.server=selectUpdateServer(current||settings.server,updateConfig.server);await releaseUpdater.check();}catch(e){updateStatus('暂不能检查更新：'+e.message);}}}
function setAutoStart(){if(app.isPackaged){try{app.setLoginItemSettings(loginItemSettings(settings.autoStart));}catch(e){send('notice','设置开机启动失败：'+e.message);}}}
let heartbeatBusy=false,externalQueue=[];
async function heartbeat(){if(heartbeatBusy||!session?.device)return;heartbeatBusy=true;const owner=key();try{const p=await request('/api/heartbeat',{version:app.getVersion(),policy:settings.fleetPolicy?.revision||0,network:DeviceNetwork.collect()});if(owner!==key())return;if(['default','adobe','inspect'].includes(p.mode)&&Array.isArray(p.extensions)&&typeof p.watch==='boolean'){const normalized={...p,keywords:Array.isArray(p.keywords)&&p.keywords.length?p.keywords:DEFAULT_KEYWORDS};const changed=settings.fleetPolicy?.revision!==normalized.revision;settings.fleetPolicy=normalized;await save('settings',settings);if(changed)await resume();notify();}}catch(e){logLifecycle('heartbeat-failed',{message:e.message});}finally{heartbeatBusy=false;}}
async function cleanSelected(paths,reason){if(!paths.length)return;externalBusy=true;notify();const owner=key();return monitor.enqueue(async()=>{const sum={files:0,fields:0,failed:0,scanned:0,skipped:0,matched:0},skippedDetails=[];let inspectOnly=true;try{for(const item of paths){if(key()!==owner)throw Error('电脑身份已变化');try{const r=await performScan(item,reason);skippedDetails.push(...(r.skippedDetails||[]));for(const k of Object.keys(sum))sum[k]+=r[k]||0;inspectOnly=inspectOnly&&r.inspect;}catch(error){const tasks=account().failedTasks||(account().failedTasks={});tasks[item]={file:item,error:error.message,time:new Date().toISOString()};const r={id:require('node:crypto').randomUUID(),files:0,fields:0,failed:1,scanned:1,skipped:0,reason,policyRevision:settings.fleetPolicy?.revision||0};history.push({owner,folder:item,time:new Date().toISOString(),...r,details:[{file:item,error:error.message,status:'失败',sourceProcessed:false}]});history=history.slice(-1000);pending.push({owner,data:r});await queueFileDetails(owner,r.id,[{file:item,error:error.message,status:'失败',sourceProcessed:false}],new Date().toISOString());await save('history',history);await save('pending',pending);sum.failed++;sum.scanned++;inspectOnly=inspectOnly&&settings.fleetPolicy?.mode==='inspect';}}await save('settings',settings);await sync().catch(e=>send('notice','统计待同步：'+e.message));await showCompletion({...sum,inspect:inspectOnly,skippedDetails});}finally{busy=false;externalBusy=false;notify();if(installPending)await startPendingUpdate();}});}
async function drainExternal(){if(!session||installing||busy||externalBusy||manualBatch||webJob?.running||!externalQueue.length)return;const paths=externalQueue.splice(0);try{await cleanSelected(paths,'右键清理');}catch(e){send('notice',e.message);}if(installPending)await startPendingUpdate();}
ipcMain.handle('install-context',async()=>{if(!app.isPackaged)throw Error('请在安装后的客户端启用');settings.contextStatus=await ContextClean.install();settings.contextInstalledPath=process.execPath;settings.contextVersion=app.getVersion();await save('settings',settings);notify();return state();});
ipcMain.handle('retry-failed',async(_,file)=>{if(!session||busy||externalBusy||installing||manualBatch||webJob?.running)throw Error('请等待当前任务完成');const tasks=account().failedTasks||{};const paths=file?(tasks[file]?[file]:[]):Object.keys(tasks);await cleanSelected(paths,'失败重试');return state();});
ipcMain.handle('state',()=>state());
ipcMain.handle('device-name',async(_,value)=>{if(!session?.device)throw Error('电脑身份尚未准备好');const name=typeof value==='string'?value.trim():'';if(!name||name.length>80||/[\x00-\x1f\x7f]/.test(name))throw Error('用户名需为1至80个字符');settings.deviceDisplayName=name;settings.deviceNameConfirmed=true;session.name=name;await save('settings',settings);notify();const pendingLogin=deviceLoginTask?.promise;Promise.resolve(pendingLogin).catch(()=>{}).then(()=>authenticateDevice()).catch(e=>send('notice','用户名已保存在本机，连接恢复后同步：'+e.message));return state();});
ipcMain.handle('device-connect',async(_,value)=>{if(connectionManager)return changeConnection('manual',value);if(busy||externalBusy||webJob?.running||installing||manualBatch||choosingInputs)throw Error('请等待当前任务结束');const server=normalizeServer(value).origin;monitor.stop();await useDevice(server);if(releaseUpdater)releaseUpdater.server=selectUpdateServer(server,updateConfig.server);await resume();try{await authenticateDevice();await heartbeat();await sync();return {ok:true,message:'已连接服务器',state:state()};}catch(e){return {ok:false,message:e.message+'；本机可继续使用，记录将在连接恢复后同步。',state:state()};}});
ipcMain.handle('open-page',async(_,page)=>{if(!['login','work'].includes(page))throw Error('Invalid page');if(page==='work'&&!session)throw Error('Please log in');await win.loadFile('index.html');notify();});
ipcMain.handle('auth',async(_,d)=>{nextSyncAt=0;if(busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('扫描期间无法切换账号');const u=normalizeServer((d.server||settings.server||updateConfig.server).trim());const ctx={server:u.origin,username:d.username};if(app.isPackaged&&u.origin==='http://127.0.0.1:8787')await ensureLocalService();if(d.register)await request('/api/register',d,ctx);const r=await request('/api/login',d,ctx);monitor.stop();session={...ctx,token:r.token,name:r.name};settings.server=ctx.server;if(releaseUpdater)releaseUpdater.server=selectUpdateServer(ctx.server,updateConfig.server);if(accountOrigin(ctx.server)===accountOrigin(updateConfig.server))({history,pending}=migrateAccount(settings,history,pending,{...session,server:accountOrigin(ctx.server)}));await save('history',history);await save('pending',pending);await save('settings',settings);await remember();await resume();await sync().catch(()=>{});return state();});
ipcMain.handle('change-password',async(_,data)=>{if(busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('Please wait for scan completion');await request('/api/password',data);monitor.stop();session=null;await save('session',{});});
ipcMain.handle('logout',async()=>{if(busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('请等待扫描结束');monitor.stop();session=null;await save('session',{});await win.loadFile('login.html');notify();});
ipcMain.handle('web-download',async(_,input)=>{
 if(!session)throw Error('请先登录');if(busy||externalBusy||webJob?.running||installing||manualBatch||choosingInputs)throw Error('请等待当前任务结束');
 const {webUrl,downloadImages,cleanImage}=require('./web-images');const url=webUrl(String(input||'').trim()),owner=key();webController=new AbortController();webJob={owner,url,running:true,phase:'等待当前扫描结束',done:0,total:0};notify();
 // Keep download, metadata writes and history commits in the same queue as folder scans.
 return monitor.enqueue(async()=>{try{
  const jobPolicy=settings.fleetPolicy||{};const result=await downloadImages(url,{desktop:app.getPath('desktop'),fetcher:(url,options)=>process.platform==='darwin'?electronNet.fetch(url,{...options,bypassCustomProtocolHandlers:true}):fetch(url,options),allowedExtensions:jobPolicy.extensions,cleanFile:async file=>{if(jobPolicy.mode==='inspect'){const tags=await tool.read(file,['-G1','-a']);return {fields:0,detected:[],inspect:true};}if(jobPolicy.mode==='adobe'){const events=[];const r=await scan(file,tool,e=>events.push(e),rewritePdf,jobPolicy);if(r.failed)throw Error(events.find(e=>e.error)?.error||'清理失败');return {fields:r.fields,detected:events[0]?.detected||[]};}return cleanImage(file,tool);},signal:webController.signal,onProgress:data=>{Object.assign(webJob,data);notify();}});
  if(result.files||result.failed){const {folder,details,id,fields,files,failed,scanned,skipped}=result;history.push({owner,folder:folder||'',reason:'网页图片清理',time:new Date().toISOString(),id,fields,files,failed,scanned,skipped,details});history=history.slice(-1000);await save('history',history);await queueFileDetails(owner,id,details,new Date().toISOString());pending.push({owner,scanIdentities:[...new Set(details.map(r=>ScanInventory.identity(r.file)))],data:{id,fields,files,failed,scanned,skipped,reason:jobPolicy.mode==='inspect'?'网页图片（仅检测）':'网页图片清理',policyRevision:jobPolicy.revision||0}});await save('pending',pending);await sync().catch(e=>send('notice','统计待同步：'+e.message));}
  webJob.result=result;webJob.phase=result.cancelled?'已停止':result.failed||result.skipped?'处理结束，部分图片未完成':'处理完成';
  const r=await dialog.showMessageBox(win,{type:result.failed||!result.downloaded?'warning':'info',title:'网页图片',message:result.cancelled?'任务已停止':result.downloaded?'图片已清理并保存到桌面':'没有成功保存的图片',detail:`保存 ${result.downloaded} 张，重复 ${result.duplicates} 张，失败 ${result.failed} 张，未处理 ${result.skipped} 张。`+(result.folder?'\n'+result.folder:''),buttons:result.folder?['完成','打开文件夹']:['完成'],defaultId:0,cancelId:0});if(r.response===1&&result.folder){const error=await shell.openPath(result.folder);if(error)send('notice','无法打开文件夹：'+error);}
  return state();
 }catch(error){webJob.phase='处理未完成';webJob.error=webController.signal.aborted?'任务已停止':error.message;send('notice',webJob.error);await dialog.showMessageBox(win,{type:webController.signal.aborted?'info':'warning',title:'网页图片',message:webController.signal.aborted?'任务已停止':'图片下载未完成',detail:webJob.error,buttons:['知道了']});return state();}finally{webJob.running=false;webController=null;notify();if(installPending)await startPendingUpdate();}});
});
ipcMain.handle('web-cancel',()=>{if(webJob?.running&&webJob.owner===key()){webController?.abort();webJob.phase='正在停止…';notify();}});
ipcMain.handle('web-open',async()=>{if(!session||webJob?.owner!==key()||webJob.running||!webJob.result?.folder)throw Error('没有可打开的结果文件夹');const error=await shell.openPath(webJob.result.folder);if(error)throw Error('无法打开文件夹：'+error);});
ipcMain.handle('open-history-file',async(_,file)=>{if(!session)throw Error('请先登录');if(typeof file!=='string'||!history.some(r=>r.owner===key()&&!r.cleared&&(r.details||[]).some(e=>e.file===file)))throw Error('此文件不在当前账号的本机历史中');let info;try{info=await fs.lstat(file);}catch{throw Error('文件已移动或删除，无法打开');}if(!info.isFile()||info.isSymbolicLink())throw Error('文件不可用，无法打开');const error=await shell.openPath(file);if(error)throw Error('无法打开文件：'+error);});
ipcMain.handle('clear-history',async()=>{if(!session)throw Error('请先登录');if(busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('请等待当前扫描结束');const owner=key();const result=await dialog.showMessageBox(win,{type:'warning',title:'清空历史记录',message:'清空本机历史展示？',buttons:['取消','清空历史记录'],defaultId:0,cancelId:0});if(result.response!==1)return state();if(key()!==owner||busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('账号或扫描状态已变化，请重试');history=clearLocalDetails(history,owner);await save('history',history);notify();return state();});
ipcMain.handle('choose',async(_,mode='folders')=>{if(!session)throw Error('请先登录');if(busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('请等待当前扫描结束');const options=require('./native-selection').selectionOptions(mode,process.platform);choosingInputs=true;try{const r=await dialog.showOpenDialog(win,options);if(r.canceled||!r.filePaths.length){choosingInputs=false;if(installPending)await startPendingUpdate();return [];}return r.filePaths;}catch(error){choosingInputs=false;throw error;}});
ipcMain.handle('picker-done',async(_,accepted)=>{if(!accepted){choosingInputs=false;if(installPending)await startPendingUpdate();}return true;});
ipcMain.handle('picker-browse',async(_,input)=>{if(!session)throw Error('请先登录');choosingInputs=true;const shortcuts=[];for(const [type,name] of [['desktop','桌面'],['documents','文稿'],['downloads','下载'],['home','用户目录']]){try{shortcuts.push({name,path:app.getPath(type)});}catch{}}if(process.platform==='win32'){for(const location of [process.execPath,app.getPath('home')]){const drive=path.parse(location).root;if(drive&&!shortcuts.some(s=>s.path===drive))shortcuts.push({name:drive,path:drive});}}let defaultPath=app.getPath('desktop');try{await fs.access(defaultPath);}catch{defaultPath=app.getPath('home');}return require('./picker-files').browse(input,{defaultPath,shortcuts});});
function editFolders(){if(!session)throw Error('请先登录');if(busy||externalBusy||webJob?.running||installing||manualBatch)throw Error('请等待当前扫描结束');return accountFolders(account());}
async function saveFolders(folders){const notices=Object.fromEntries(Object.entries(account().firstScanNotices||{}).filter(([path])=>folders.some(f=>f.path===path)));settings.accounts[key()]={...account(),folders,firstScanNotices:notices};await save('settings',settings);await resume();return state();}
ipcMain.handle('folder',async(_,value)=>{
 choosingInputs=true;try{
 const folders=editFolders(),owner=key(),selection=await require('./scan-inputs').prepareInputs(value,folders);
 if(selection.files.length)await monitor.enqueue(async()=>{
  const skippedDetails=[];let inspectOnly=true;const totals={files:0,fields:0,failed:0,scanned:0,skipped:0,matched:0};
  try{
   for(const file of selection.files){
    if(key()!==owner)throw Error('Account changed; please drop the file again');
    if(!session||installing)throw Error('处理已中断，请稍后重新拖入文件');
    const result=await performScan(file,'单文件清理');skippedDetails.push(...(result.skippedDetails||[]));inspectOnly=inspectOnly&&result.inspect;
    for(const key of Object.keys(totals))totals[key]+=result[key]||0;
   }
   settings.accounts[owner]={...account(),scanSummary:{mode:'files',roots:selection.files.length,time:new Date().toISOString(),totals}};await save('settings',settings);notify();
   await showCompletion({...totals,inspect:inspectOnly,skippedDetails});
  }finally{busy=false;notify();if(installPending)await startPendingUpdate();}
 });
 if(key()!==owner)throw Error('Account changed; please drop the selection again');
 if(selection.directories.length&&!installing){const notices={...account().firstScanNotices};for(const added of selection.folders)if(!folders.some(f=>overlaps(f.path,added.path)&&overlaps(added.path,f.path)))notices[added.path]=true;settings.accounts[owner]={...account(),firstScanNotices:notices};return saveFolders(selection.folders);}
 return state();
 }finally{choosingInputs=false;if(installPending)await startPendingUpdate();}
});
ipcMain.handle('monitor',async(_,data)=>{const folders=editFolders();const folder=folders.find(f=>f.path===data.path);if(!folder)throw Error('文件夹不存在');folder.enabled=!!data.enabled;return saveFolders(folders);});
ipcMain.handle('remove-folder',async(_,folder)=>{const folders=editFolders();return saveFolders(folders.filter(f=>f.path!==folder));});
ipcMain.handle('rescan',(_,folder)=>{if(!session)throw Error('请先登录');if(installing||busy||externalBusy||webJob?.running||manualBatch)throw Error('请等待当前扫描结束');const paths=accountFolders(account()).filter(f=>(f.enabled||settings.fleetPolicy?.watch===false)&&(!folder||f.path===folder)).map(f=>f.path);if(!paths.length)throw Error('没有可扫描的目录，请先恢复监听');manualBatch={owner:key(),remaining:new Set(paths),roots:paths.length,totals:ScanResults.empty(),failedRoots:0};for(const root of paths)monitor.enqueue(async()=>{if(manualBatch)manualBatch.currentRoot=root;await performScan(root,'手动扫描');});notify();return state();});
ipcMain.handle('autostart',async(_,enabled)=>{settings.autoStart=!!enabled;setAutoStart();await save('settings',settings);notify();return state();});
ipcMain.handle('update-check',checkUpdate);
ipcMain.handle('diagnose-network',async(_,value)=>{const url=normalizeServer(value).origin+'/api/health';const nodeFetch=createClientFetch({fetcher:fetch,version:()=>app.getVersion(),transport:'node-diagnostic'});return await Promise.all([['应用网络',clientFetch],['基础网络',nodeFetch]].map(async([name,fetcher])=>{try{const response=await fetcher(url,{signal:AbortSignal.timeout(6000)});const body=await response.json();return name+'：HTTP '+response.status+'，数据库 '+(body.database||'未识别');}catch(e){return name+'：'+e.message;}}));});
ipcMain.handle('open-backend',async(_,url)=>{await shell.openExternal(normalizeServer(url).origin);});
ipcMain.handle('local-backend',async()=>{if(!localService)throw Error('当前没有内置本机后台');await shell.openExternal(localService.url);if(localService.credentials)await dialog.showMessageBox(win,{type:'info',title:'本机测试后台账号',message:'管理员账号：'+localService.credentials.username,detail:'管理员密码：'+localService.credentials.password+'\n此账号仅用于这台电脑的本机后台。请勿公开分享。'});});
if(!app.requestSingleInstanceLock())app.quit();else{
 app.on('second-instance',(_,argv)=>{const paths=ContextClean.selected(argv||[]);if(paths.length){externalQueue.push(...paths);drainExternal();}else if(win)show();});
 app.whenReady().then(async()=>{
  Menu.setApplicationMenu(null);
  settings=await read('settings',settings);pending=await read('pending',[]);history=await read('history',[]);filePending=await read('pending-files',[]);
  // Migrate old pending batches to the new account key without losing counts.
  pending=pending.map(e=>e.server?{owner:e.server+'|'+e.owner,data:e.data}:e);
  win=new BrowserWindow({width:1280,height:920,minWidth:760,minHeight:640,show:false,backgroundColor:'#080f1c',autoHideMenuBar:true,icon:path.join(__dirname,'app-icon.png'),webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
  win.removeMenu();win.on('hide',()=>logLifecycle('window-hidden'));win.on('closed',()=>logLifecycle('window-closed'));win.webContents.on('render-process-gone',(_,detail)=>logLifecycle('renderer-gone',{reason:detail.reason,exitCode:detail.exitCode}));
  // Preserve Mac editing shortcuts after removing the framework's default menu.
  win.webContents.on('before-input-event',(event,input)=>{if(process.platform!=='darwin'||input.type!=='keyDown'||!input.meta||input.alt||input.control)return;const key=input.key.toLowerCase();const command={a:'selectAll',c:'copy',v:'paste',x:'cut',z:input.shift?'redo':'undo'}[key];if(command){event.preventDefault();win.webContents[command]();}else if(key==='q'){event.preventDefault();if(!busy&&!webJob?.running&&!manualBatch){quitting=true;app.quit();}else send('notice','请等待扫描结束后退出');}});
  win.webContents.setWindowOpenHandler(()=>({action:'deny'}));win.webContents.on('will-navigate',e=>e.preventDefault());win.on('close',e=>{if(!quitting){e.preventDefault();win.hide();}});
  const icon=makeTrayIcon();tray=new Tray(icon);tray.setToolTip('净元 · 文件自动清理');tray.setContextMenu(Menu.buildFromTemplate([{label:'打开净元 / 工作历史',click:show},{label:'立即检查升级',click:()=>{show();checkUpdate();}},{type:'separator'},{label:'退出净元',click:()=>{if(busy||externalBusy||webJob?.running||manualBatch){send('notice','正在处理文件，请等待结束后退出');show();return;}quitting=true;app.quit();}}]));tray.on('click',show);tray.on('double-click',show);nativeTheme.on?.('updated',()=>{if(tray&&!tray.isDestroyed?.())tray.setImage(makeTrayIcon());});
  setAutoStart();
  externalQueue.push(...ContextClean.selected(process.argv));initConnection();await useDevice(connectionManager.logicalOrigin);await resume();await win.loadFile('index.html');
  if(shouldShowWindow({argv:process.argv,platform:process.platform,wasOpenedAsHidden:process.platform==='darwin'&&app.getLoginItemSettings().wasOpenedAsHidden}))show();notify();

  releaseUpdater=new ReleaseUpdater({server:selectUpdateServer(settings.server,updateConfig.server),publicKey:updateConfig.publicKey,fetcher:clientFetch,alternateFetcher:async manifest=>{
   const m=connectionManager;if(!m?.current||m.logicalOrigin!==LAN)throw Error('没有可用的公司备用入口');
   const alternate=m.current===LAN?WAN:LAN,probe=await m.probe(alternate);
   if(!probe.id||probe.id!==m.expectedId)throw Error('备用入口无法连接或服务器身份不匹配');
   const suffix='/api/updates/'+manifest.platform+'/'+manifest.arch+(manifest.platform==='win32'?'?format=zip&base='+app.getVersion():'');
   const response=await rawClientFetch(alternate+suffix,{signal:AbortSignal.timeout(15000),redirect:'error'});m.checkResponse(response);
   if(!response.ok)throw Error('备用入口版本信息不可用');
   const other=verifyManifest(await response.json(),updateConfig.publicKey,manifest.platform,manifest.arch);
   for(const field of ['version','url','size','sha256'])if(other[field]!==manifest[field])throw Error('内外网更新版本或文件不一致');
   return async(url,options)=>{const target=new URL(url);const result=await rawClientFetch(alternate+target.pathname+target.search,options);m.checkResponse(result);return result;};
  },version:app.getVersion(),cache:path.join(app.getPath('userData'),'updates'),userData:app.getPath('userData'),onStatus:updateStatus,onReady:async()=>{installPending=true;if(busy)updateStatus('新版已下载，当前扫描结束后自动安装');else await startPendingUpdate();}});await confirmUpdateStartup();connectionManager.check({force:true}).then(()=>checkUpdate()).catch(e=>logLifecycle('connection-check-failed',{message:e.message}));connectionTimer=setInterval(()=>connectionManager.check().catch(e=>logLifecycle('connection-check-failed',{message:e.message})),connectionManager.options.tickMs);setInterval(checkUpdate,10*60*1000);setInterval(heartbeat,60000);setInterval(drainExternal,2000);drainExternal();if(app.isPackaged&&!process.execPath.includes('/AppTranslocation/')&&(settings.contextInstalledPath!==process.execPath||settings.contextVersion!==app.getVersion()))ContextClean.install().then(async message=>{settings.contextInstalledPath=process.execPath;settings.contextVersion=app.getVersion();settings.contextStatus=message;await save('settings',settings);notify();}).catch(()=>{});setInterval(()=>{if(session&&!busy&&(pending.some(e=>e.owner===key())||filePending.some(e=>e.owner===key())))sync().catch(e=>logLifecycle('sync-retry',{message:e.message}));},1000);
 }).catch(e=>{logLifecycle('startup-failed',{error:e.stack||e.message});dialog.showErrorBox('启动失败',e.message);quitting=true;app.quit();});
 app.on('activate',()=>{if(win&&!backgroundStartup)show();});app.on('window-all-closed',()=>{});app.on('before-quit',()=>{logLifecycle('before-quit',{installing,quitting});quitting=true;if(connectionTimer)clearInterval(connectionTimer);monitor.stop();localService?.child?.kill();tool.end();});
}
