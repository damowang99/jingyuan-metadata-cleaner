function skippedSummary(result){const rows=result.skippedDetails||[];if(!rows.length)return '';const lines=rows.slice(0,5).map(r=>String(r.file).split(/[\\/]/).pop()+'：'+r.reason);if(rows.length>5)lines.push('另有 '+(rows.length-5)+' 个文件，可点击“查看跳过清单”查看全部。');return '\n\n跳过文件：\n'+lines.join('\n');}
function completionMessage(result){
 if(result.inspect)return {type:result.failed?'warning':'info',title:'文件清理结果',message:'检测完成（未修改文件）',detail:`检查 ${result.scanned||0} 个文件，命中 ${result.matched||0} 个，跳过 ${result.skipped||0} 个，失败 ${result.failed||0} 个。当前统一策略为仅检测。`+skippedSummary(result),buttons:['知道了'],defaultId:0,cancelId:0};
 const {files=0,fields=0,failed=0,scanned=0,skipped=0}=result;
 const unchanged=Math.max(0,scanned-files-failed-skipped);
 const message=failed?(files?'部分文件处理失败':'文件处理失败'):files?'源文件已处理':skipped&&!unchanged?'文件未处理':'未发现需要清理的目标元数据';
 const detail=[`已检查 ${scanned} 个文件，成功处理 ${files} 个源文件，清除 ${fields} 个字段。`];
 if(files)detail.push('处理成功的源文件已复核并覆盖，可直接使用。');
 if(unchanged)detail.push(`${unchanged} 个文件未发现需要清理的目标元数据，原文件无需修改。`);
 if(skipped)detail.push(result.skippedDetails?.length?`${skipped} 个文件已跳过，原文件未修改。`:`${skipped} 个文件格式暂不支持，已跳过，原文件未修改。`);
 if(failed)detail.push(`${failed} 个文件处理失败，请查看工作历史中的失败原因。`);
 return {type:failed||skipped?'warning':'info',title:'文件清理结果',message,detail:detail.join('\n')+skippedSummary(result),buttons:['知道了'],defaultId:0,cancelId:0,noLink:true};
}
module.exports={completionMessage};
