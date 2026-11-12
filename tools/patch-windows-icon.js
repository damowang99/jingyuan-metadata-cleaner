// Resource-only PE editing for cross-platform builds; retain code and ASAR integrity data.
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const PE=require('../desktop/node_modules/pe-library'),ResEdit=require('../desktop/node_modules/resedit');
const hash=data=>crypto.createHash('sha256').update(Buffer.from(data||[])).digest('hex');
const remaining=entries=>JSON.stringify(entries.filter(e=>e.type!==3&&e.type!==14).map(e=>[e.type,e.id,e.lang,hash(e.bin)]).sort());
function iconBytes(icon){return Buffer.from(icon.isRaw()?icon.bin:icon.generate());}
async function patch(context){
 if(context.electronPlatformName!=='win32')return;
 const file=path.join(context.appOutDir,'Metadata Cleaner.exe'),iconFile=ResEdit.Data.IconFile.from(await fs.readFile(path.join(context.appDir||context.packager.info.appDir,'assets/app.ico')));
 const exe=PE.NtExecutable.from(await fs.readFile(file)),resource=PE.NtExecutableResource.from(exe);
 const entryPoint=exe.newHeader.optionalHeader.addressOfEntryPoint;
 const originalSections=exe.getAllSections().filter(s=>s.info.name!=='.rsrc').map(s=>({name:s.info.name,hash:hash(s.data),address:s.info.virtualAddress})),originalResources=remaining(resource.entries),imageBase=exe.getImageBase();
 const groups=ResEdit.Resource.IconGroupEntry.fromEntries(resource.entries);
 for(const group of groups.length?groups:[{id:1,lang:1033}])ResEdit.Resource.IconGroupEntry.replaceIconsForResource(resource.entries,group.id,group.lang,iconFile.icons.map(item=>item.data));
 resource.outputResource(exe);const result=Buffer.from(exe.generate()),verified=PE.NtExecutable.from(result),res=PE.NtExecutableResource.from(verified);
 if(remaining(res.entries)!==originalResources||verified.getImageBase()!==imageBase||verified.newHeader.optionalHeader.addressOfEntryPoint!==entryPoint)throw Error('Unexpected non-icon resource change');
 for(const previous of originalSections){const section=verified.getAllSections().find(s=>s.info.name===previous.name);if(!section||hash(section.data)!==previous.hash||(previous.name!=='.reloc'&&section.info.virtualAddress!==previous.address))throw Error('Unexpected executable section change: '+previous.name);}
 const reloc=verified.getAllSections().find(s=>s.info.name==='.reloc');if(reloc&&verified.getSectionByEntry(5)!==reloc)throw Error('Relocation directory mismatch');
 const expected=iconFile.icons.map(item=>hash(iconBytes(item.data))).sort();
 for(const group of ResEdit.Resource.IconGroupEntry.fromEntries(res.entries)){const actual=group.getIconItemsFromEntries(res.entries).map(item=>hash(iconBytes(item))).sort();if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Embedded icon does not match approved ICO');}
 await fs.writeFile(file,result);console.log('Windows icon embedded; native code and integrity resources unchanged');
}
module.exports=patch;
