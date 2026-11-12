function selectionOptions(mode='folders',platform=process.platform){
 const kind=mode==='both'&&platform!=='darwin'?'files':mode;
 if(!['both','files','folders'].includes(kind))throw Error('无效的选择类型');
 return {title:kind==='both'?'选择文件或文件夹':kind==='files'?'选择要清理的文件':'选择要监听的文件夹',properties:kind==='both'?['openFile','openDirectory','multiSelections']:[kind==='files'?'openFile':'openDirectory','multiSelections']};
}
module.exports={selectionOptions};
