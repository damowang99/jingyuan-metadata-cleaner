const crypto=require('node:crypto'),path=require('node:path');
function identity(file,platform=process.platform){const api=platform==='win32'?path.win32:path;let normalized=api.resolve(file).normalize('NFC');if(platform==='win32')normalized=normalized.toLowerCase();return crypto.createHash('sha256').update('scan-path-v1\0'+platform+'\0'+normalized).digest('hex');}
module.exports={identity};
