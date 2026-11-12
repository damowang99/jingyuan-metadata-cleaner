const{test}=require('node:test'),assert=require('node:assert/strict');
const{DEFAULT_KEYWORDS,isAdobeMetadata,isCleanupTarget}=require('../desktop/matcher');
const{targets}=require('../desktop/scanner');

test('server keywords select software provenance and lineage case-insensitively',()=>{
 const metadata={'XMP:CreatorTool':'StudioX Render 3','XMP:DerivedFrom':'StudioX project','XMP:Description':'StudioX is mentioned in user text','XMP-dc:Creator':'StudioX'};
 assert.deepEqual(targets(metadata,{keywords:['studiox']}),['XMP:CreatorTool','XMP:DerivedFrom']);
 assert.equal(isAdobeMetadata('XMP:CreatorTool','StudioX Render 3',['Other']),false);
});

test('default words preserve common Adobe detection and do not change image credit cleanup rules',()=>{
 assert.ok(DEFAULT_KEYWORDS.includes('Adobe'));
 assert.equal(isAdobeMetadata('XMP:CreatorTool','Adobe Illustrator 2026'),true);
 assert.equal(isCleanupTarget('IPTC:Credit','StudioX',{image:true,keywords:['Other']}),true);
 assert.equal(isCleanupTarget('XMP:Description','Adobe Photoshop',{image:true,keywords:['Photoshop']}),false);
});
