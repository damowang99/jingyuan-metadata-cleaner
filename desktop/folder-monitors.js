const path=require('node:path');
const {DirectoryMonitor}=require('./monitor');
function comparable(value,platform=process.platform){return platform==='win32'?value.toLowerCase():value;}
function overlaps(a,b,platform=process.platform){const api=platform==='win32'?path.win32:path;const relative=api.relative(comparable(a,platform),comparable(b,platform));return relative===''||(!relative.startsWith('..'+api.sep)&&relative!=='..'&&!api.isAbsolute(relative));}
function accountFolders(account={}){return Array.isArray(account.folders)?account.folders.map(f=>({path:f.path,enabled:f.enabled!==false})):account.folder?[{path:account.folder,enabled:account.enabled!==false}]:[];}
class FolderMonitors{
 constructor({run,onChange=()=>{},onError=()=>{},onWarning=()=>{},...options}){Object.assign(this,{run,onChange,onError,onWarning,options});this.items=new Map();this.tail=Promise.resolve();this.scanning='';}
 restore(folders){const enabled=new Set(folders.filter(f=>f.enabled).map(f=>f.path));for(const [folder,monitor] of this.items){if(!enabled.has(folder)){monitor.stop();this.items.delete(folder);}}for(const folder of enabled){if(this.items.has(folder))continue;let monitor;monitor=new DirectoryMonitor({...this.options,onState:()=>this.onChange(),onWarning:message=>{this.onWarning(folder+'：'+message);this.onChange();},onError:error=>{this.onError(Error(folder+'：'+error.message));this.onChange();},run:(root,reason)=>{const task=this.tail.catch(()=>{}).then(async()=>{if(this.items.get(root)!==monitor||!monitor.active)return;this.scanning=root;this.onChange();try{await this.run(root,reason);}finally{this.scanning='';this.onChange();}});this.tail=task;return task;}});this.items.set(folder,monitor);try{monitor.start(folder);monitor.trigger('启动补扫');}catch(e){this.items.delete(folder);this.onError(e);}}this.onChange();}
 enqueue(run){const task=this.tail.catch(()=>{}).then(run);this.tail=task;return task;}
 trigger(folder,reason='手动扫描'){if(folder){this.items.get(folder)?.trigger(reason);}else for(const m of this.items.values())m.trigger(reason);this.onChange();}
 status(folder){const m=this.items.get(folder);return {monitoring:!!m?.active,mode:m?.mode||'',scanning:this.scanning===folder,queued:!!m?.active&&(!!m.dirty||(m.running&&this.scanning!==folder))};}
 stop(){for(const m of this.items.values())m.stop();this.items.clear();this.onChange();}
}
module.exports={FolderMonitors,accountFolders,overlaps};
