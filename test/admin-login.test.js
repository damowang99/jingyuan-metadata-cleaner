const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../server/web/login.js'),'utf8'),key='jingyuan.admin.remembered-login.v1';
function setup(storage=new Map(),fail=false){
 const elements=new Map();for(const id of ['username','password','remember','reveal','authform','login','status','remember-hint'])elements.set(id,{value:'',type:id==='password'?'password':'text',checked:false,disabled:false,attrs:{},setAttribute(k,v){this.attrs[k]=v;}});
 const redirects=[],requests=[];const localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 vm.runInNewContext(source,{JingUI:{paint(){}},document:{getElementById:id=>elements.get(id)},localStorage,location:{replace:p=>redirects.push(p)},fetch:async(url,options)=>{requests.push({url,options});return {ok:url.endsWith('/session')?false:!fail,json:async()=>({error:'账号或密码错误'})};}});
 return {$:id=>elements.get(id),storage,redirects,requests};
}
test('remember explicitly saves successful credentials and restores them on the next visit',async()=>{
 const s=setup();s.$('username').value='admin-test';s.$('password').value='local-test-only';s.$('remember').checked=true;await s.$('authform').onsubmit({preventDefault(){}});
 assert.equal(JSON.parse(s.storage.get(key)).password,'local-test-only');assert.deepEqual(s.redirects,['./']);
 const next=setup(s.storage);assert.equal(next.$('username').value,'admin-test');assert.equal(next.$('password').value,'local-test-only');assert.equal(next.$('remember').checked,true);assert.equal(next.$('password').type,'password');
 next.$('reveal').onclick();assert.equal(next.$('password').type,'text');assert.equal(next.$('reveal').attrs['aria-pressed'],'true');next.$('reveal').onclick();assert.equal(next.$('password').type,'password');
 next.$('remember').checked=false;next.$('remember').onchange();assert.equal(s.storage.has(key),false);assert.equal(setup(s.storage).$('password').value,'');
});
test('unchecked or failed login never stores a new password, malformed saved data is discarded',async()=>{
 const plain=setup();plain.$('password').value='not-remembered';await plain.$('authform').onsubmit({preventDefault(){}});assert.equal(plain.storage.has(key),false);
 const failed=setup(new Map(),true);failed.$('username').value='test';failed.$('password').value='wrong';failed.$('remember').checked=true;await failed.$('authform').onsubmit({preventDefault(){}});assert.equal(failed.storage.has(key),false);assert.deepEqual(failed.redirects,[]);assert.equal(failed.$('status').textContent,'账号或密码错误');
 const bad=new Map([[key,'{broken']]);assert.equal(setup(bad).$('password').value,'');assert.equal(bad.has(key),false);
});
