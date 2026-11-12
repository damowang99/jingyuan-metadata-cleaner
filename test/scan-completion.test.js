const {test}=require('node:test'),assert=require('node:assert/strict');
const {completionMessage}=require('../desktop/scan-completion');
test('completion confirms replacement only when files were actually cleaned',()=>{
 const success=completionMessage({scanned:2,files:2,fields:7});assert.equal(success.message,'源文件已处理');assert.match(success.detail,/成功处理 2 个源文件，清除 7 个字段/);assert.match(success.detail,/复核并覆盖/);
 const clean=completionMessage({scanned:1});assert.match(clean.message,/未发现/);assert.match(clean.detail,/原文件无需修改/);assert.doesNotMatch(clean.detail,/已复核并覆盖/);
 const unsupported=completionMessage({scanned:1,skipped:1});assert.equal(unsupported.message,'文件未处理');assert.match(unsupported.detail,/暂不支持/);assert.doesNotMatch(unsupported.detail,/已复核并覆盖/);
 const partial=completionMessage({scanned:3,files:1,fields:2,failed:1,skipped:1});assert.equal(partial.message,'部分文件处理失败');assert.equal(partial.type,'warning');assert.match(partial.detail,/1 个文件处理失败/);
 const failed=completionMessage({scanned:1,failed:1});assert.equal(failed.message,'文件处理失败');assert.doesNotMatch(failed.detail,/已复核并覆盖/);
});
test('completion names skipped files with reasons and bounds the popup while preserving full list',()=>{const skippedDetails=Array.from({length:8},(_,i)=>({file:'/private/folder/file'+i+'.txt',reason:'格式暂不支持（.txt）'}));const message=completionMessage({scanned:8,skipped:8,skippedDetails});assert.match(message.detail,/file0.txt：格式暂不支持/);assert.match(message.detail,/file4.txt/);assert.doesNotMatch(message.detail,/file5.txt|\/private/);assert.match(message.detail,/另有 3 个文件/);assert.match(completionMessage({inspect:true,scanned:1,skipped:1,skippedDetails:skippedDetails.slice(0,1)}).detail,/file0.txt/);});
