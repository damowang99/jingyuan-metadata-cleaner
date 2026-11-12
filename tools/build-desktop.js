// Build the desktop source after installing dependencies and preparing native helpers.
const path=require('node:path'),fs=require('node:fs');
const project=path.resolve(__dirname,'../desktop'),platform=process.argv[2]||process.platform;
if(process.argv.includes('--help')){console.log('node tools/build-desktop.js win32 <windows-python-directory>\nnode tools/build-desktop.js darwin');process.exit(0);}
const builder=require(path.join(project,'node_modules/electron-builder'));
const config={afterPack:require('./patch-windows-icon'),beforePack:require('./verify-platform-components')};
let targets;
if(platform==='win32'){
 const runtime=path.resolve(process.argv[3]||path.join(project,'bin/windows-python'));
 for(const file of ['python.exe','python312.dll','python312._pth','pdf_clean.py'])if(!fs.existsSync(path.join(runtime,file)))throw Error('Missing Windows Python runtime component: '+file);
 config.win={signAndEditExecutable:false};config.extraResources=[{from:runtime,to:'bin/windows-python'}];
 config.artifactName='Metadata-Cleaner-Setup-${version}-win-x64.${ext}';
 config.nsis={oneClick:false,allowToChangeInstallationDirectory:true,perMachine:false,deleteAppDataOnUninstall:false,runAfterFinish:false};
 targets=builder.Platform.WINDOWS.createTarget(['nsis'],builder.Arch.x64);
}else if(platform==='darwin'){
 if(process.platform!=='darwin')throw Error('Build Mac packages on macOS');
 config.mac={identity:null,notarize:false};targets=builder.Platform.MAC.createTarget(['dir'],builder.Arch.arm64);
}else throw Error('Supported platforms: win32, darwin');
builder.build({projectDir:project,targets,publish:'never',config}).catch(error=>{console.error(error);process.exitCode=1;});
