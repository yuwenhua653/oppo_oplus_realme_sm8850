import importlib.util,os,json,pathlib,subprocess,tempfile,unittest,types,struct
import shutil
HERE=pathlib.Path(__file__).resolve().parent
P=HERE/'source_dt.py'
s=importlib.util.spec_from_file_location('source_dt',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
FULL=os.environ.get('MYRON_TEST_FULL')
FULL_STATUS=os.environ.get('MYRON_TEST_BUILD_STATUS')
DTC=os.environ.get('MYRON_TEST_DTC','dtc')
TOOLS=types.SimpleNamespace(**{name:os.environ.get('MYRON_TEST_'+name.upper(),name) for name in ['fdtoverlay','fdtoverlaymerge','fdtput','mkdtboimg']})
def compile_dt(root,name,text):
 src=root/(name+'.dts');out=root/name;src.write_text(text);subprocess.run([str(DTC),'-@','-I','dts','-O','dtb','-o',str(out),str(src)],check=True,capture_output=True);return out
def full_fixture(root):
 full=root/'full';full.mkdir();(full/'base.dtb').write_bytes(b'original')
 profile={'bases':[{'file':'base.dtb','overlays':[]}],'board_overlays':[],'dts_commit':'test-dts'}
 identity={'kernel_release':'test-release','linux_banner':'Linux version test-release'}
 status={**identity,'success':True,'entry_commit':json.loads((HERE/'modules.json').read_text())['entry_commit'],
         'sources':[{'path':'vendor/qcom/sm8850-devicetrees','commit':profile['dts_commit']}]}
 (full/'validation-status.json').write_text(json.dumps({**identity,'verified':True}))
 (full/'artifact-manifest.json').write_text(json.dumps({**identity,'files':[{'file':'base.dtb','bytes':8,'sha256':m.sha(full/'base.dtb')}]}))
 build_status=root/'build-status.json';build_status.write_text(json.dumps(status))
 return full,profile,build_status,status
class Test(unittest.TestCase):
 def test_full_catalog_requires_matching_build_provenance(self):
  with tempfile.TemporaryDirectory() as t:
   full,profile,build_status,status=full_fixture(pathlib.Path(t))
   self.assertEqual(m.catalog(full,profile,build_status)[1],[])
   with self.assertRaisesRegex(ValueError,'requires --build-status'):m.catalog(full,profile)
   for field,bad in [('success',False),('entry_commit','old-entry'),('sources',[]),
                     ('sources',[{'path':'vendor/qcom/sm8850-devicetrees','commit':'old-dts'}]),
                     ('sources',status['sources']*2),('kernel_release','old-release'),('linux_banner','old-banner')]:
    build_status.write_text(json.dumps({**status,field:bad}))
    with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):m.catalog(full,profile,build_status)
   build_status.write_text(json.dumps(status))
   for name in ['validation-status.json','artifact-manifest.json']:
    path=full/name;original=path.read_text();record=json.loads(original)
    for field in ['kernel_release','linux_banner']:
     path.write_text(json.dumps({**record,field:'mismatched'}))
     with self.subTest(name=name,field=field),self.assertRaisesRegex(ValueError,'mismatch'):m.catalog(full,profile,build_status)
    path.write_text(original)
   self.assertEqual(m.catalog(full,profile,build_status)[1],[])
 def test_reviewed_foundry_matching_is_narrow(self):
  profile=json.loads((HERE/'dt-profile.json').read_text());rules=m.reviewed_rules(profile)
  for rev in (0x10000,0x20000):
   base=(0x1010295,rev);generic=(0x1000295,rev)
   self.assertEqual(m.overlay_match(base,{generic,base},rules),('exact',base))
   self.assertEqual(m.overlay_match(base,{generic},rules),('reviewed_foundry_zero',generic))
   self.assertEqual(m.overlay_match(base,{generic},set()),(None,None))
   for wrong in [(0x1000294,rev),(0x295,rev),(0x2000295,rev),(0x1020295,rev),(0x1000295,rev+1)]:
    self.assertEqual(m.overlay_match(base,{wrong},rules),(None,None))
   for wrong in [(0x1020295,rev),(0x1010294,rev),(0x2010295,rev),(0x1010295,rev+1)]:
    self.assertEqual(m.overlay_match(wrong,{generic},rules),(None,None))
  for bad in [dict(base_msm_id=[0x1020295,0x10000],overlay_msm_id=[0x1000295,0x10000],evidence='DT-ID-MATCHING.md'),
              dict(base_msm_id=[0x1010295,0x10000],overlay_msm_id=[0x1000295,0x20000],evidence='DT-ID-MATCHING.md'),
              dict(base_msm_id=[0x1010295,0x10000],overlay_msm_id=[0x1000295,0x10000],evidence='')]:
   with self.assertRaises(ValueError):m.reviewed_rules({'reviewed_foundry_zero':[bad]})
  with self.assertRaises(ValueError):m.reviewed_rules({'reviewed_foundry_zero':profile['reviewed_foundry_zero']*2})
 def test_compiled_catalog_rejects_tampering_and_stale_pins(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);(root/'base.dtb').write_bytes(b'original')
   profile={'bases':[{'file':'base.dtb','overlays':[]}],'board_overlays':[],'dts_commit':'test-dts'}
   manifest={'kind':'host-dtc-only','dts_commit':'test-dts','entry_commit':json.loads((HERE/'modules.json').read_text())['entry_commit'],
             'files':[{'file':'base.dtb','bytes':8,'sha256':m.sha(root/'base.dtb')}]}
   def save():(root/'dt-compile.json').write_text(json.dumps(manifest))
   save();self.assertEqual(m.compiled_catalog(root,profile)[1],[])
   (root/'base.dtb').write_bytes(b'tampered')
   with self.assertRaisesRegex(ValueError,'hash mismatch'):m.compiled_catalog(root,profile)
   (root/'base.dtb').write_bytes(b'original')
   for key in ['entry_commit','dts_commit','kind']:
    old=manifest[key];manifest[key]='stale';save()
    with self.assertRaises(ValueError):m.compiled_catalog(root,profile)
    manifest[key]=old
   manifest['files'][0]['file']='../base.dtb';save()
   with self.assertRaisesRegex(ValueError,'filename'):m.compiled_catalog(root,profile)
 def test_invalid_bounds(self):
  for data in [b'',bytes(40),struct.pack('>10I',0xd00dfeed,40,40,0,0,17,16,0,0,100)]:
   with self.assertRaises(ValueError):m.fdt(data)
 @unittest.skipUnless(FULL and FULL_STATUS, 'Set MYRON_TEST_FULL and MYRON_TEST_BUILD_STATUS to the R115 output/status')
 def test_current_source_rejected(self):
  profile=json.loads((P.parent/'dt-profile.json').read_text())
  with self.assertRaisesRegex(ValueError,'Full kernel entry mismatch'):m.catalog(pathlib.Path(FULL),profile,pathlib.Path(FULL_STATUS))
 def test_no_stale_images_after_failure(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);full,profile,build_status,status=full_fixture(root);out=root/'output';out.mkdir()
   status['entry_commit']='old-entry';build_status.write_text(json.dumps(status))
   for args in [[],['--build-status',str(build_status)]]:
    for n in ['dtb.img','dtbo.img','fastrpc-order-proof.json']:(out/n).write_bytes(b'stale')
    p=subprocess.run(['python3','-B',str(P),'--full',str(full),'--output',str(out),*args],capture_output=True)
    self.assertEqual(p.returncode,1);self.assertFalse((out/'dtb.img').exists());self.assertFalse((out/'dtbo.img').exists());self.assertFalse((out/'fastrpc-order-proof.json').exists());self.assertFalse(json.loads((out/'source-dt-report.json').read_text())['success'])
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
 def test_typed_hardware_properties_reject_regressions(self):
  required={'/sound':{'gpio':{'phandle_target':'/pin'}},'/haptics':{'brake':{'hex':'00'},'disabled':{'hex':''}},'/camera':{'gpios':[604,617]}}
  nodes={'/sound':{'gpio':struct.pack('>I',23)},'/pin':{'phandle':struct.pack('>I',23)},'/haptics':{'brake':b'\x00','disabled':b''},'/camera':{'gpios':struct.pack('>2I',604,617)}}
  self.assertEqual(m.property_errors(nodes,required),[])
  for path,key,bad in [('/sound','gpio',struct.pack('>I',24)),('/sound','gpio',bytes(4)),('/sound','gpio',bytes(8)),('/haptics','brake',bytes(4)),('/haptics','disabled',b'1'),('/camera','gpios',b'bad')]:
   previous=nodes[path][key];nodes[path][key]=bad
   with self.subTest(path=path,key=key,bad=bad):self.assertIn(path+':'+key,m.property_errors(nodes,required))
   nodes[path][key]=previous
  del nodes['/haptics']['disabled'];self.assertIn('/haptics:disabled',m.property_errors(nodes,required));nodes['/haptics']['disabled']=b''
  nodes['/duplicate']={'phandle':struct.pack('>I',23)};self.assertIn('/sound:gpio',m.property_errors(nodes,required));del nodes['/duplicate']
  nodes['/pin']={'linux,phandle':struct.pack('>I',23)};self.assertEqual(m.property_errors(nodes,required),[])
  with self.assertRaisesRegex(ValueError,'Unknown required-property'):m.property_errors(nodes,{'/sound':{'gpio':{'unsupported':True}}})
 def test_disabled_parent_blocks_provider(self):
  self.assertEqual(m.provider_errors({'/':{},'/bus':{'status':b'disabled\0'},'/bus/dev':{'compatible':b'test,provider\0'}},['test,provider']),['test,provider'])
 def test_managed_spi_pm_scope_and_ownership(self):
  path='/soc/spi@1a80000';prop='qcom,system-suspend-managed'
  node={prop:b'', 'qcom,la-vm':b'', 'status':b'ok\0'}
  self.assertEqual(m.managed_spi_pm_errors({path:node},[path]),[])
  self.assertTrue(m.managed_spi_pm_errors({},[path]))
  self.assertTrue(m.managed_spi_pm_errors({path:node,'/other':node},[path]))
  for key,bad in [(prop,b'1'),('qcom,la-vm',b'1'),('status',b'disabled\0'),('qcom,le-vm',b''),('qcom,shared_ee',b''),('qcom,shared_se',b'')]:
   with self.subTest(key=key):self.assertTrue(m.managed_spi_pm_errors({path:{**node,key:bad}},[path]))
  missing_la=dict(node);del missing_la['qcom,la-vm']
  self.assertTrue(m.managed_spi_pm_errors({path:missing_la},[path]))

class NativeCatalogTests(unittest.TestCase):
 def setUp(self):
  self.profile={'bases':[{'file':'base.dtb','overlays':['tech.dtbo']}], 'board_overlays':['board.dtbo']}
 def test_selects_declared_native_outputs(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'sub').mkdir()
   for name in ('base.dtb','tech.dtbo','board.dtbo','unused.dtbo'):(root/'sub'/name).write_bytes(b'fixture')
   files,missing=m.native_catalog(root,self.profile)
   self.assertEqual(set(files),{'base.dtb','tech.dtbo','board.dtbo'});self.assertEqual(missing,[])
 def test_missing_and_duplicate_outputs(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'base.dtb').write_bytes(b'fixture')
   self.assertEqual(m.native_catalog(root,self.profile)[1],['board.dtbo','tech.dtbo'])
   (root/'sub').mkdir();(root/'sub/base.dtb').write_bytes(b'fixture')
   with self.assertRaisesRegex(ValueError,'Duplicate native'):m.native_catalog(root,self.profile)
 def test_rejects_redirected_output(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'payload').write_bytes(b'fixture');(root/'base.dtb').symlink_to(root/'payload')
   with self.assertRaisesRegex(ValueError,'Redirected native'):m.native_catalog(root,self.profile)

if __name__=='__main__':unittest.main(verbosity=2)
