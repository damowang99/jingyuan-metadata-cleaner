JingUI.paint();
const $=id=>document.getElementById(id);
const rememberedLoginKey='jingyuan.admin.remembered-login.v1';
function forgetSavedLogin(){try{localStorage.removeItem(rememberedLoginKey);}catch{}}
function restoreSavedLogin(){
 try{const raw=localStorage.getItem(rememberedLoginKey);if(!raw)return;const saved=JSON.parse(raw);if(saved.version!==1||typeof saved.username!=='string'||!saved.username||typeof saved.password!=='string'||!saved.password){forgetSavedLogin();return;}$('username').value=saved.username;$('password').value=saved.password;$('remember').checked=true;}catch{forgetSavedLogin();}
}
restoreSavedLogin();
$('reveal').onclick=()=>{const shown=$('password').type==='password';$('password').type=shown?'text':'password';$('reveal').setAttribute('aria-label',shown?'隐藏密码':'显示密码');$('reveal').setAttribute('aria-pressed',String(shown));};
$('remember').onchange=()=>{if(!$('remember').checked)forgetSavedLogin();};
async function request(url,data){const r=await fetch(url,{method:data?'POST':'GET',credentials:'same-origin',headers:{'Content-Type':'application/json'},...(data?{body:JSON.stringify(data)}:{})});const b=await r.json();if(!r.ok)throw Error(b.error||'登录失败');return b;}
$('authform').onsubmit=async e=>{
 e.preventDefault();if($('login').disabled)return;$('login').disabled=true;
 const username=$('username').value,password=$('password').value,remember=$('remember').checked;
 try{await request('/api/admin/login',{username,password,remember});
  if(remember){try{localStorage.setItem(rememberedLoginKey,JSON.stringify({version:1,username,password}));}catch{forgetSavedLogin();$('remember-hint').textContent='浏览器禁止本地保存，密码未记住。请允许此站点保存数据后重试。';$('status').textContent='登录成功，但无法保存密码。';return;}}else forgetSavedLogin();
  $('password').value='';location.replace('./');
 }catch(e){$('status').textContent=e.message;}finally{$('login').disabled=false;}
};
request('/api/admin/session').then(()=>location.replace('./')).catch(()=>{});
