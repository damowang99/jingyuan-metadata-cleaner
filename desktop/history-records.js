function clearLocalDetails(history,owner){
 const keys=['id','owner','time','fields','files','failed','scanned','skipped'];
 return history.map(record=>record.owner!==owner?record:{...Object.fromEntries(keys.filter(key=>record[key]!==undefined).map(key=>[key,record[key]])),cleared:true});
}
function localTotals(history,owner){return history.filter(r=>r.owner===owner&&!r.cleared).reduce((total,r)=>({files:total.files+(Number(r.files)||0),fields:total.fields+(Number(r.fields)||0),failed:total.failed+(Number(r.failed)||0)}),{files:0,fields:0,failed:0});}
module.exports={clearLocalDetails,localTotals};
