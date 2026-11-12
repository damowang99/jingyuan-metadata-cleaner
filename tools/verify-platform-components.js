const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
async function verify(context){
 if(context.electronPlatformName!=='win32')return;
 const root=path.join(context.appDir||context.packager.info.appDir,'node_modules','exiftool-vendored.exe'),manifest=require('./windows-exiftool-13.34.0.manifest.json');
 let pkg;try{pkg=JSON.parse(await fs.readFile(path.join(root,'package.json'),'utf8'));}catch{throw Error('Missing Windows ExifTool. Build on Windows, or install exiftool-vendored.exe@13.34.0 with --no-save --package-lock=false --force before cross-building on Mac.');}
 if(pkg.version!==manifest.version)throw Error('Windows ExifTool version differs from the verified component manifest');
 for(const[name,expected]of Object.entries(manifest.files)){const file=path.join(root,name);let data;try{data=await fs.readFile(file);}catch{throw Error('Missing Windows ExifTool component: '+name);}if(data.length!==expected.size||crypto.createHash('sha256').update(data).digest('hex')!==expected.sha256)throw Error('Windows ExifTool component mismatch: '+name);}
 console.log('Verified complete Windows ExifTool package: '+Object.keys(manifest.files).length+' files');
}
module.exports=verify;
if(require.main===module)verify({appDir:path.resolve(__dirname,'../desktop'),electronPlatformName:process.argv[2]||process.platform}).catch(error=>{console.error(error.message);process.exitCode=1;});
