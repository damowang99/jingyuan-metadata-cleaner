import hashlib,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import pikepdf
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'desktop/pdf_clean.py'

class PdfQualityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name);self.src=self.folder/'中文 原件.pdf';self.dst=self.folder/'中文 已清理.pdf'
 def make_pdf(self,with_xmp=True,attachments=False,outline=False,form=False,large=False):
  pdf=pikepdf.Pdf.new();pdf.add_blank_page();pdf.docinfo['/Producer']='Adobe PDF library';pdf.docinfo['/Creator']='Adobe Illustrator';pdf.docinfo['/Author']='Adobe Brand Team';pdf.docinfo['/Title']='Adobe 活动描述'
  if with_xmp:
   with pdf.open_metadata(set_pikepdf_as_editor=False,update_docinfo=False) as metadata:
    metadata['xmp:CreatorTool']='Adobe Photoshop';metadata['dc:description']='Adobe 品牌宣传';metadata['dc:creator']=['Adobe Brand Team']
  if attachments:pdf.attachments['说明.txt']=pikepdf.AttachedFileSpec(pdf,b'keep attachment',filename='说明.txt')
  if outline:
   with pdf.open_outline() as tree:tree.root.append(pikepdf.OutlineItem('第一章',0))
  if form:
   field=pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name('/Tx'),T=pikepdf.String('Name'),V=pikepdf.String('保留表单')));pdf.Root.AcroForm=pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array([field])))
  if large:pdf.Root.BigBlob=pdf.make_stream(os.urandom(12_000_000))
  pdf.save(self.src)
 def clean(self):return subprocess.run([sys.executable,str(SCRIPT),str(self.src),str(self.dst)],capture_output=True,text=True)
 def test_plain_pdf_and_xmp_preserve_user_text(self):
  self.make_pdf();original=self.src.read_bytes();result=self.clean();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.src.read_bytes(),original)
  with pikepdf.open(self.dst) as pdf:
   self.assertEqual(len(pdf.pages),1);self.assertNotIn('/Producer',pdf.docinfo);self.assertNotIn('/Creator',pdf.docinfo);self.assertEqual(str(pdf.docinfo['/Author']),'Adobe Brand Team');self.assertEqual(str(pdf.docinfo['/Title']),'Adobe 活动描述')
   metadata=dict(pdf.open_metadata());self.assertNotIn('{http://ns.adobe.com/xap/1.0/}CreatorTool',metadata);self.assertEqual(metadata['{http://purl.org/dc/elements/1.1/}description'],'Adobe 品牌宣传')
 def test_plain_pdf_without_xmp(self):
  self.make_pdf(with_xmp=False);before=self.src.read_bytes();result=self.clean();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.src.read_bytes(),before)
  with pikepdf.open(self.dst) as pdf:
   self.assertEqual(len(pdf.pages),1);self.assertNotIn('/Creator',pdf.docinfo);self.assertNotIn('/Producer',pdf.docinfo);self.assertEqual(str(pdf.docinfo['/Author']),'Adobe Brand Team')
 def test_attachments_bookmarks_forms_and_large_pdf(self):
  self.make_pdf(attachments=True,outline=True,form=True,large=True);result=self.clean();self.assertEqual(result.returncode,0,result.stderr)
  with pikepdf.open(self.dst) as pdf:
   self.assertEqual(bytes(pdf.attachments['说明.txt'].get_file().read_bytes()),b'keep attachment');self.assertEqual(len(pdf.open_outline().root),1);self.assertEqual(str(pdf.Root.AcroForm.Fields[0].V),'保留表单');self.assertGreater(len(pdf.Root.BigBlob.read_bytes()),10_000_000)
 def test_signed_pdf_skips_without_output_or_source_change(self):
  self.make_pdf();pdf=pikepdf.open(self.src,allow_overwriting_input=True);signature=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name('/Sig'),ByteRange=pikepdf.Array([0,1,2,3])));pdf.Root.Signature=signature;pdf.save(self.src);before=hashlib.sha256(self.src.read_bytes()).digest();result=self.clean();self.assertNotEqual(result.returncode,0);self.assertIn('已签名PDF不处理',result.stderr);self.assertFalse(self.dst.exists());self.assertEqual(hashlib.sha256(self.src.read_bytes()).digest(),before)
 def test_encrypted_pdf_skips_without_output_or_source_change(self):
  self.make_pdf();pdf=pikepdf.open(self.src,allow_overwriting_input=True);pdf.save(self.src,encryption=pikepdf.Encryption(owner='owner-password',user='user-password'));before=hashlib.sha256(self.src.read_bytes()).digest();result=self.clean();self.assertNotEqual(result.returncode,0);self.assertIn('加密PDF不处理',result.stderr);self.assertFalse(self.dst.exists());self.assertEqual(hashlib.sha256(self.src.read_bytes()).digest(),before)

if __name__=='__main__':unittest.main()
