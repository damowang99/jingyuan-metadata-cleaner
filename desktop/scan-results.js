(function(root){
function empty(){return {scanned:0,skipped:0,files:0,fields:0,failed:0};}
function add(total,result){for(const k of Object.keys(empty()))total[k]+=(Number(result[k])||0);return total;}
function counts(result){const r={...empty(),...result};return {...r,checked:Math.max(0,r.scanned-r.skipped),unchanged:Math.max(0,r.scanned-r.skipped-r.files-r.failed)};}
function format(summary){if(!summary)return '';const r=counts(summary.totals);const scope=summary.mode==='files'?'文件清理':summary.mode==='manual'?'手动扫描':'后台扫描';return `最近一次${scope}完成${summary.roots?'（'+summary.roots+' 个'+(summary.mode==='files'?'文件':'目录')+'）':''}：发现 ${r.scanned} 个文件，检查 ${r.checked} 个，处理 ${r.files} 个，清除 ${r.fields} 个字段；无需清理 ${r.unchanged} 个，跳过 ${r.skipped} 个，失败 ${r.failed} 个${summary.failedRoots?'；另有 '+summary.failedRoots+' 个目录扫描失败':''}`;}
function formatLocal(stats={}){return `本机历史累计：已处理 ${Number(stats.files)||0} 个文件，清除 ${Number(stats.fields)||0} 个字段，失败 ${Number(stats.failed)||0} 个`;}
const api={empty,add,counts,format,formatLocal};if(typeof module!=='undefined')module.exports=api;else root.ScanResults=api;
})(globalThis);
