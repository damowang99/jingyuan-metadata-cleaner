const passwordDialog=document.getElementById('password-dialog');let passwordSubmitting=false;
document.getElementById('password-open').onclick=()=>{if(authenticated)passwordDialog.showModal();};
function closePassword(){if(!passwordSubmitting)passwordDialog.close();}
for(const id of ['password-close','password-cancel'])document.getElementById(id).onclick=closePassword;
passwordDialog.addEventListener('cancel',e=>{if(passwordSubmitting)e.preventDefault();});
passwordDialog.addEventListener('close',()=>{document.getElementById('change-password').reset();document.getElementById('password-feedback').textContent='';});
document.getElementById('change-password').onsubmit=async e=>{e.preventDefault();if(passwordSubmitting)return;const old=document.getElementById('current-pass'),next=document.getElementById('new-pass'),confirm=document.getElementById('confirm-pass'),feedback=document.getElementById('password-feedback');if(next.value!==confirm.value){feedback.textContent='两次新密码不一致';return;}passwordSubmitting=true;for(const id of ['password-submit','password-close','password-cancel'])document.getElementById(id).disabled=true;
try{await api('/api/password',{currentPassword:old.value,newPassword:next.value});try{localStorage.removeItem('jingyuan.admin.remembered-login.v1');}catch{}passwordSubmitting=false;passwordDialog.close();location.replace('login.html');}catch(e){feedback.textContent=e.message;}finally{passwordSubmitting=false;for(const id of ['password-submit','password-close','password-cancel'])document.getElementById(id).disabled=false;}};
