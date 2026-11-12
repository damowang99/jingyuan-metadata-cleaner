function updateToken(argv){const arg=argv.find(value=>value.startsWith('--update-ack='));const token=arg?.slice('--update-ack='.length);return /^[a-f0-9]{32}$/.test(token||'')?token:null;}
function isBackgroundUpdate({argv,platform}){return argv.includes('--background-after-update')||(platform==='darwin'&&!!updateToken(argv)&&!argv.includes('--show-after-update'));}
function shouldShowWindow({argv,platform,wasOpenedAsHidden=false}){
 if(isBackgroundUpdate({argv,platform})||argv.includes('--context-clean'))return false;
 if(updateToken(argv)||argv.includes('--show-after-update'))return true;
 // Previous releases registered hidden login launches; show those too after upgrading.
 return true;
}
function loginItemSettings(enabled){return {openAtLogin:!!enabled,openAsHidden:false,args:['--autostart']};}
function presentWindow(win,app,{platform=process.platform,afterUpdate=false}={}){
 if(win.isMinimized())win.restore();
 if(platform==='win32')win.setSkipTaskbar(false);
 win.show();win.moveTop();win.focus();
 if(platform==='darwin'&&afterUpdate)app.focus({steal:true});
}
module.exports={loginItemSettings,updateToken,isBackgroundUpdate,shouldShowWindow,presentWindow};
