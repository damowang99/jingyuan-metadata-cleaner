const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');const {browse}=require('../desktop/picker-files');
test('mixed selector resets a failed address, clears stale selections on navigation and returns selected folder or cancel',async()=>{
 const temp=await fs.mkdtemp(path.join(os.tmpdir(),'cleaner-mixed-ui-')),root=await fs.realpath(temp),folder=path.join(root,'folder');
 try{await fs.mkdir(folder);await fs.writeFile(path.join(root,'sample.jpg'),'test');
 const ids=new Map(),done=[];function el(tag='div'){return {tag,children:[],value:'',checked:false,disabled:false,setAttribute(){},addEventListener(){},showModal(){this.open=true;},close(){this.open=false;},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},querySelectorAll(){return this.children.flatMap(row=>row.children.filter(item=>item.tag==='input'));}};}
 const html=await fs.readFile(path.join(__dirname,'../desktop/index.html'),'utf8');for(const [,id]of html.matchAll(/id="([^"]+)"/g))ids.set(id,el());const $=id=>ids.get(id),ctx={document:{getElementById:$,createElement:el},cleaner:{browse:input=>browse(input,{defaultPath:root}),pickerDone:async accepted=>done.push(accepted)}};vm.createContext(ctx);vm.runInContext(await fs.readFile(path.join(__dirname,'../desktop/file-picker.js'),'utf8'),ctx);
 const promise=ctx.MixedPicker.open();for(let i=0;i<100&&!$('picker-items').children.length;i++)await new Promise(r=>setTimeout(r,5));assert.equal($('picker-items').children.length,2);
 const check=$('picker-items').children[1].children[0];check.checked=true;check.onchange();assert.equal($('picker-confirm').disabled,false);
 $('picker-path').value=path.join(root,'missing');await $('picker-go').onclick();assert.equal($('picker-path').value,root);assert.equal($('picker-confirm').disabled,false);
 $('picker-path').value=folder;await $('picker-go').onclick();assert.equal($('picker-confirm').disabled,true);await $('picker-current').onclick();assert.equal(JSON.stringify(await promise),JSON.stringify([folder]));assert.equal(done.at(-1),true);
 const cancel=ctx.MixedPicker.open();await $('picker-cancel').onclick();assert.equal(JSON.stringify(await cancel),'[]');assert.equal(done.at(-1),false);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
