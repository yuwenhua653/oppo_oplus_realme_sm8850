import importlib.util,os,json,pathlib,subprocess,tempfile,unittest,types,struct
import shutil
HERE=pathlib.Path(__file__).resolve().parent
P=HERE/'source_dt.py'
s=importlib.util.spec_from_file_location('source_dt',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
FULL=os.environ.get('MYRON_TEST_FULL')
DTC=os.environ.get('MYRON_TEST_DTC','dtc')
TOOLS=types.SimpleNamespace(**{name:os.environ.get('MYRON_TEST_'+name.upper(),name) for name in ['fdtoverlay','fdtoverlaymerge','fdtput','mkdtboimg']})
def compile_dt(root,name,text):
 src=root/(name+'.dts');out=root/name;src.write_text(text);subprocess.run([str(DTC),'-@','-I','dts','-O','dtb','-o',str(out),str(src)],check=True,capture_output=True);return out
class Test(unittest.TestCase):
 def test_invalid_bounds(self):
  for data in [b'',bytes(40),struct.pack('>10I',0xd00dfeed,40,40,0,0,17,16,0,0,100)]:
   with self.assertRaises(ValueError):m.fdt(data)
 @unittest.skipUnless(FULL, 'Set MYRON_TEST_FULL to the verified R115 output directory')
 def test_current_source_rejected(self):
  profile=json.loads((P.parent/'dt-profile.json').read_text());files,missing=m.catalog(pathlib.Path(FULL),profile);trees,errors=m.preflight(files,profile,missing)
  self.assertEqual(missing,['canoe-camera.dtbo']);self.assertTrue(any('gpu_niden_en' in e.get('symbols',[]) for e in errors))
 @unittest.skipUnless(FULL, 'Set MYRON_TEST_FULL to the verified R115 output directory')
 def test_no_stale_images_after_failure(self):
  with tempfile.TemporaryDirectory() as t:
   out=pathlib.Path(t)
   for n in ['dtb.img','dtbo.img']:(out/n).write_bytes(b'stale')
   p=subprocess.run(['python3','-B',str(P),'--full',str(pathlib.Path(FULL)),'--output',str(out)],capture_output=True)
   self.assertEqual(p.returncode,1);self.assertFalse((out/'dtb.img').exists());self.assertFalse((out/'dtbo.img').exists());self.assertFalse(json.loads((out/'source-dt-report.json').read_text())['success'])
 @unittest.skipUnless(all(shutil.which(x) for x in [DTC,*vars(TOOLS).values()]), 'dtc, fdtoverlay, fdtoverlaymerge, fdtput and mkdtboimg required')
 def test_eight_variant_pack_roundtrip(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);files={};spec=[];allids=' '.join(f'{100+i} 1' for i in range(8))
   for i in range(8):
    n=f'base{i}.dtb';files[n]=compile_dt(root,n,f'/dts-v1/; / {{ model="test base {i}"; compatible="test,base"; qcom,msm-id=<{100+i} 1>; qcom,board-id=<0 0>; provider: provider {{ compatible="test,provider"; }}; }};');spec.append({'file':n,'msm_id':[100+i,1],'board_id':[0,0],'overlays':['tech.dtbo']})
   files['tech.dtbo']=compile_dt(root,'tech.dtbo',f'/dts-v1/; /plugin/; / {{ qcom,msm-id=<{allids}>; qcom,board-id=<0 0>; }}; &provider {{ status="okay"; }};')
   files['board.dtbo']=compile_dt(root,'board.dtbo',f'/dts-v1/; /plugin/; / {{ model="test board"; compatible="test,board"; qcom,msm-id=<{allids}>; qcom,board-id=<8 0>; xiaomi,miboard-id=<4 0>; }}; &provider {{ test-value=<7>; }};')
   files['extra.dtbo']=compile_dt(root,'extra.dtbo',f'/dts-v1/; /plugin/; / {{ model="wrong if metadata not restored"; qcom,msm-id=<{allids}>; }}; &provider {{ test-extra=<9>; }};')
   profile={'bases':spec,'board_overlays':['board.dtbo','extra.dtbo'],'board_metadata_from':'board.dtbo','required_compatible':['test,provider'],'dtbo_table':{'page_size':4096,'version':0,'id':0,'rev':0,'custom':[0,0,0,0]}}
   trees,errors=m.preflight(files,profile,[]);self.assertFalse(errors)
   out=root/'output';out.mkdir();result=m.assemble(files,trees,profile,out,TOOLS);self.assertEqual(set(result),{'dtb.img','dtbo.img'})
   data=(out/'dtb.img').read_bytes();off=0
   for i in range(8):
    size=struct.unpack_from('>I',data,off+4)[0];node=m.fdt(data[off:off+size])['/'];self.assertEqual(m.cells(node['qcom,msm-id']),[100+i,1]);off+=size
   self.assertEqual(off,len(data));m.verify_table((out/'dtbo.img').read_bytes(),(out/'work/myron-board.dtbo').read_bytes(),profile['dtbo_table'])
   profile['bases'][1]['required_compatible']=['test,wrong-gpu-revision']
   with self.assertRaisesRegex(ValueError,'test,wrong-gpu-revision'):m.assemble(files,trees,profile,root/'wrong-revision',TOOLS)
   del profile['bases'][1]['required_compatible']
   profile['required_compatible']=['test,absent']
   with self.assertRaisesRegex(ValueError,'Missing/disabled hardware'):m.assemble(files,trees,profile,root/'failed',TOOLS)
   self.assertFalse((root/'failed/dtb.img').exists())
 def test_required_binding_properties(self):
  required={'/macro':{'reg':[0x6ac0000,0]}}
  self.assertEqual(m.property_errors({'/macro':{}},required),['/macro:reg'])
  self.assertEqual(m.property_errors({'/macro':{'reg':struct.pack('>2I',0x6ac0000,0)}},required),[])
 def test_disabled_parent_blocks_provider(self):
  self.assertEqual(m.provider_errors({'/':{},'/bus':{'status':b'disabled\0'},'/bus/dev':{'compatible':b'test,provider\0'}},['test,provider']),['test,provider'])
if __name__=='__main__':unittest.main(verbosity=2)
