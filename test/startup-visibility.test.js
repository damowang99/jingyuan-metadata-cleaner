const {test}=require('node:test'),assert=require('node:assert/strict');
const {loginItemSettings,updateToken,shouldShowWindow,presentWindow}=require('../desktop/startup-visibility');
test('background update stays hidden, legacy Windows visibility remains compatible',()=>{
 const ack='--update-ack='+'a'.repeat(32);
 for(const platform of ['win32','darwin']){
  assert.equal(shouldShowWindow({argv:['--hidden',ack],platform,wasOpenedAsHidden:true}),platform==='win32');
  assert.equal(shouldShowWindow({argv:['--hidden','--show-after-update'],platform,wasOpenedAsHidden:true}),true);
  assert.equal(shouldShowWindow({argv:['--hidden'],platform}),true);assert.equal(shouldShowWindow({argv:['--autostart'],platform}),true);
  assert.equal(shouldShowWindow({argv:[],platform}),true);assert.equal(shouldShowWindow({argv:[ack,'--background-after-update'],platform}),false);
 }
 assert.equal(shouldShowWindow({argv:[],platform:'darwin',wasOpenedAsHidden:true}),true);assert.deepEqual(loginItemSettings(true),{openAtLogin:true,openAsHidden:false,args:['--autostart']});assert.equal(loginItemSettings(false).openAtLogin,false);
 assert.equal(updateToken(['--update-ack=../../invalid']),null);
 assert.equal(updateToken([ack]),'a'.repeat(32));
});
test('window presentation restores a minimized window, shows its taskbar entry and raises it',()=>{
 const calls=[],win={isMinimized:()=>true,restore:()=>calls.push('restore'),setSkipTaskbar:value=>calls.push(['taskbar',value]),show:()=>calls.push('show'),moveTop:()=>calls.push('top'),focus:()=>calls.push('focus')};
 presentWindow(win,{}, {platform:'win32',afterUpdate:true});
 assert.deepEqual(calls,['restore',['taskbar',false],'show','top','focus']);
 calls.length=0;presentWindow(win,{focus:options=>calls.push(options)},{platform:'darwin',afterUpdate:true});
 assert.deepEqual(calls,['restore','show','top','focus',{steal:true}]);
});
