const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {prepareInputs}=require('../desktop/scan-inputs'),{scan}=require('../desktop/scanner'),{FolderMonitors}=require('../desktop/folder-monitors');
test('mixed drops deduplicate files, exclude selected directory descendants and reject links before changing folders',async()=>{
 const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cleaner-input-')));
 try{
  const dir=path.join(root,'folder'),file=path.join(root,'single.jpg');await fs.mkdir(dir);await fs.writeFile(file,'original');await fs.writeFile(path.join(dir,'nested.jpg'),'original');
  const result=await prepareInputs([file,file,dir,path.join(dir,'nested.jpg')]);assert.deepEqual(result.files,[file]);assert.deepEqual(result.folders,[{path:dir,enabled:true}]);
  const current=[{path:dir,enabled:false}];await assert.rejects(prepareInputs([root],current),/重叠/);assert.deepEqual(current,[{path:dir,enabled:false}]);
  await fs.symlink(file,path.join(root,'alias.jpg'));await assert.rejects(prepareInputs([path.join(root,'alias.jpg')]),/符号链接/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('single file scan verifies and overwrites only the selected file and reports counts',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'cleaner-single-'));
 try{
  const file=path.join(root,'single.jpg'),neighbor=path.join(root,'neighbor.jpg');await fs.writeFile(file,'original');await fs.writeFile(neighbor,'untouched');
  const events=[],result=await scan(file,{read:async f=>(await fs.readFile(f,'utf8'))==='clean'?{}:{'IFD0:Software':'Adobe Photoshop'},write:async f=>fs.writeFile(f,'clean')},e=>events.push(e));
  assert.equal(result.scanned,1);assert.equal(result.fields,1);assert.equal(result.files,1);assert.equal(result.failed,0);assert.equal(events[0].file,file);assert.equal(await fs.readFile(file,'utf8'),'clean');assert.equal(await fs.readFile(neighbor,'utf8'),'untouched');
  await fs.writeFile(file,'original');const failed=await scan(file,{read:async()=>({'IFD0:Software':'Adobe'}),write:async()=>{throw Error('write failed');}});assert.equal(failed.failed,1);assert.equal(await fs.readFile(file,'utf8'),'original');
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('one-off files share the monitor queue and continue after a failed task',async()=>{
 const monitors=new FolderMonitors({run:async()=>{}}),events=[];let release;const gate=new Promise(r=>release=r);
 const first=monitors.enqueue(async()=>{events.push('first');await gate;events.push('done');});
 const second=monitors.enqueue(async()=>{events.push('second');throw Error('failure');});const handled=second.catch(()=>{});const third=monitors.enqueue(async()=>events.push('third'));
 await new Promise(r=>setImmediate(r));assert.deepEqual(events,['first']);release();await Promise.all([first,handled,third]);assert.deepEqual(events,['first','done','second','third']);
});
