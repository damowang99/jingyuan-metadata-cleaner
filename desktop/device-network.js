const os=require('node:os'),{isIP}=require('node:net');
function collect(interfaces=os.networkInterfaces()){
 const seen=new Set(),rows=[];
 for(const [name,addresses] of Object.entries(interfaces||{}))for(const address of addresses||[]){
  if(address.internal||!isIP(address.address))continue;
  const mac=String(address.mac||'').toLowerCase();const key=name+'|'+address.address;if(seen.has(key))continue;seen.add(key);
  rows.push({name:name.slice(0,80),ip:address.address,mac:/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(mac)&&mac!=='00:00:00:00:00:00'?mac:''});
 }
 return rows.sort((a,b)=>(isIP(a.ip)===4?0:1)-(isIP(b.ip)===4?0:1)).slice(0,16);
}
module.exports={collect};
