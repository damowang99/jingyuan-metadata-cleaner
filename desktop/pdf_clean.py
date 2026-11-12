"""Rewrite PDFs after removing Adobe software provenance; never alter signed/encrypted originals."""
import re,sys
import pikepdf

ADOBE=re.compile(r'adobe|adobellustrator',re.I)
PRODUCTS=re.compile(r'\b(?:photoshop|illustrator|acrobat|indesign|lightroom|premiere(?:\s+pro)?|after\s*effects|audition|incopy|dreamweaver|fireworks|freehand|golive|pagemaker|distiller|creative\s*(?:cloud|suite)|camera\s*raw|imageready|animate|captivate|substance|bridge|xd)\b',re.I)
PROVENANCE=re.compile(r'software|creator(?:tool)?|producer|application|program|history|agent|toolkit|writername|readername|creatorsubtool',re.I)
LINEAGE=re.compile(r'documentid|instanceid|originaldocumentid|derivedfrom|manifest|documentancestors',re.I)
DESCRIPTIVE=re.compile(r'artist|author|copyright|rights|description|title|subject|keywords|caption|usercomment',re.I)

def matches(key,value):
 key=str(key);name=key.rsplit(':',1)[-1].rsplit('}',1)[-1].lstrip('/').lower()
 if DESCRIPTIVE.fullmatch(name) or name=='creator' and ('dc:' in key.lower() or '/dc/' in key.lower()):return False
 text=str(value)
 return bool((PROVENANCE.search(name) and (ADOBE.search(text) or PRODUCTS.search(text))) or (LINEAGE.search(name) and ADOBE.search(text)))

def clean_pdf(source,target):
 try:pdf=pikepdf.open(source)
 except pikepdf.PasswordError as error:raise RuntimeError('加密PDF不处理') from error
 with pdf:
  if pdf.is_encrypted:raise RuntimeError('加密PDF不处理')
  if '/Perms' in pdf.Root and '/DocMDP' in pdf.Root.Perms:raise RuntimeError('已签名PDF不处理')
  for obj in pdf.objects:
   if isinstance(obj,pikepdf.Dictionary) and (obj.get('/Type')==pikepdf.Name('/Sig') or obj.get('/FT')==pikepdf.Name('/Sig') or '/ByteRange' in obj):raise RuntimeError('已签名PDF不处理')
  for key in list(pdf.docinfo.keys()):
   if matches(key,pdf.docinfo[key]):del pdf.docinfo[key]
  if '/Metadata' in pdf.Root:
   with pdf.open_metadata(set_pikepdf_as_editor=False,update_docinfo=False) as metadata:
    for key in list(metadata.keys()):
     if matches(key,metadata[key]):del metadata[key]
  pdf.save(target)

if __name__=='__main__':
 if len(sys.argv)!=3:raise SystemExit('Usage: pdf_clean.py source.pdf target.pdf')
 clean_pdf(sys.argv[1],sys.argv[2])
