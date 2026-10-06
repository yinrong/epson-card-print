import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
def load_program():
    from importlib.machinery import SourceFileLoader
    loader=SourceFileLoader('epson_print_card',str(ROOT/'scripts/epson-print-card'))
    spec=importlib.util.spec_from_loader('epson_print_card',loader)
    obj=importlib.util.module_from_spec(spec);loader.exec_module(obj);return obj
epc=load_program()


class CardJob(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self._old_config=os.environ.get('EPSON_PRINT_CARD_CONFIG_DIR')
        os.environ['EPSON_PRINT_CARD_CONFIG_DIR']=str(self.base/'config')
        def restore():
            if self._old_config is None: os.environ.pop('EPSON_PRINT_CARD_CONFIG_DIR',None)
            else: os.environ['EPSON_PRINT_CARD_CONFIG_DIR']=self._old_config
        self.addCleanup(restore)
        self.profile=copy.deepcopy(epc.DEFAULT_PROFILE)
        self.fronts=self.base/'fronts';self.fronts.mkdir()
        for i,color in enumerate(('red','green','blue','yellow','cyan','magenta','orange','purple','brown','pink','gray')):
            Image.new('RGB',(86,54),color).save(self.fronts/f'{i:02d}-card.png')
        Image.new('RGB',(86,54),'white').save(self.base/'back.png')

    def build(self, front_count=3, group='2x5', profile=None, calibration=False):
        for extra in sorted(self.fronts.iterdir())[front_count:]:
            (self.fronts/extra.name).unlink()
        active=epc.active_profile_path();active.parent.mkdir(parents=True,exist_ok=True)
        epc.write(active,profile or self.profile)
        args=argparse.Namespace(
                                front_dir=None if calibration else str(self.fronts),
                                back_img=None if calibration else str(self.base/'back.png'),
                                group=group,output=str(self.base/'job'),calibration=calibration,dpi=150,fit='contain')
        epc.prepare(args)
        return epc.read(self.base/'job/manifest.json')

    def step_args(self, **kw):
        d=dict(job=str(self.base/'job'),queue=kw.pop('queue','EPSON_TEST'),execute=False,tray_loaded=False,confirm_output=False,confirm_dry=False)
        d.update(kw);return argparse.Namespace(**d)

    def mark_submitted(self, index):
        folder=self.base/'job';state=epc.read(folder/'state.json')
        state['events'].append({'index':index,'status':'submitted'})
        epc.write(folder/'state.json',state)

    def test_three_cards_two_trays_shared_back(self):
        m=self.build(3)
        self.assertEqual(m['mode'],'card-group')
        self.assertEqual(m['group'],{'slots_per_tray':2,'trays_per_group':5})
        self.assertEqual(m['cards'],3)
        self.assertTrue(all(c['back']==m['back_image'] for c in [c for b in m['batches'] for c in b['cards']]))
        self.assertEqual([b['group'] for b in m['batches']],[1,1])
        self.assertEqual(m['batches'][0]['sides']['front']['placements'],[{'id':'00-card','slot':'S1'},{'id':'01-card','slot':'S2'}])
        self.assertEqual(m['batches'][1]['sides']['front']['placements'],[{'id':'02-card','slot':'S1'}])
        for b in m['batches']:
            for side in ('front','back'):
                reader=PdfReader(self.base/'job'/b['sides'][side]['file'])
                self.assertEqual(len(reader.pages),1)
                self.assertAlmostEqual(float(reader.pages[0].mediabox.width)/epc.PT,self.profile['page_mm'][0],places=4)
                self.assertAlmostEqual(float(reader.pages[0].mediabox.height)/epc.PT,self.profile['page_mm'][1],places=4)
        self.assertIn('证卡组批打印',(self.base/'job/装卡顺序.html').read_text())

    def test_eleven_cards_group_split_and_event_sequence(self):
        m=self.build(11)
        self.assertEqual(len(m['batches']),6)
        self.assertEqual([b['group'] for b in m['batches']],[1,1,1,1,1,2])
        ev=[(e['type'],e.get('side'),e.get('batch'),e.get('phase')) for e in epc.job_events(m)]
        self.assertEqual(ev,[('side','front',1,None),('side','front',2,None),('side','front',3,None),('side','front',4,None),('side','front',5,None),('dry',None,None,'backs'),
                             ('side','back',1,None),('side','back',2,None),('side','back',3,None),('side','back',4,None),('side','back',5,None),('dry',None,None,'next batch'),
                             ('side','front',6,None),('dry',None,None,'backs'),('side','back',6,None),('dry',None,None,'next batch')])

    def test_dir_scan_sorted_and_rejects_bad_input(self):
        self.build(2)
        rows_dir=self.base/'fronts2';rows_dir.mkdir()
        Image.new('RGB',(10,10)).save(rows_dir/'b.png');Image.new('RGB',(10,10)).save(rows_dir/'a.png')
        cards=epc.load_cards(rows_dir,self.base/'back.png')
        self.assertEqual([c['id'] for c in cards],['a','b'])
        Image.new('RGB',(10,10)).save(rows_dir/'a.jpg')
        with self.assertRaisesRegex(ValueError,'Duplicate'):epc.load_cards(rows_dir,self.base/'back.png')
        empty=self.base/'empty';empty.mkdir()
        with self.assertRaisesRegex(ValueError,'No images'):epc.load_cards(empty,self.base/'back.png')
        with self.assertRaisesRegex(ValueError,'Not a directory'):epc.load_cards(self.base/'nope',self.base/'back.png')
        with self.assertRaisesRegex(ValueError,'Missing back'):epc.load_cards(rows_dir,self.base/'no-back.png')

    def test_group_and_profile_validation(self):
        for bad in ('3x5','2','2x0','ax5',''):
            with self.assertRaises(ValueError):epc.parse_group(bad)
        self.assertEqual(epc.parse_group('2x5'),(2,5))
        self.assertEqual(epc.parse_group('2X3'),(2,3))
        one_slot=copy.deepcopy(self.profile);one_slot['slots']=one_slot['slots'][:1];one_slot['back_slot_map']=['S1']
        with self.assertRaisesRegex(ValueError,'slots'):self.build(2,profile=one_slot)

    def test_dry_gate_waits_confirms_and_rejects_wrong_flag(self):
        self.build(3)
        for i in (0,1):
            self.mark_submitted(i);epc.step(self.step_args(confirm_output=True,queue=None))
        self.assertEqual(epc.read(self.base/'job/state.json')['next_event'],2)
        with patch.object(epc,'checked_run',side_effect=AssertionError('must not touch printer')):
            epc.step(self.step_args(queue=None))
        self.assertEqual(epc.read(self.base/'job/state.json')['next_event'],2)
        with self.assertRaisesRegex(ValueError,'drying gate'):epc.step(self.step_args(confirm_output=True,queue=None))
        epc.step(self.step_args(confirm_dry=True,queue=None))
        self.assertEqual(epc.read(self.base/'job/state.json')['next_event'],3)
        state=epc.read(self.base/'job/state.json')
        with self.assertRaisesRegex(ValueError,'No submitted'):epc.step(self.step_args(confirm_output=True,queue=None))

    def test_full_cycle_through_all_groups(self):
        m=self.build(11)
        events=epc.job_events(m);folder=self.base/'job'
        for i,ev in enumerate(events):
            if ev['type']=='dry':
                epc.step(self.step_args(confirm_dry=True,queue=None))
            else:
                self.mark_submitted(i)
                epc.step(self.step_args(confirm_output=True,queue=None))
            self.assertEqual(epc.read(folder/'state.json')['next_event'],i+1)
        with patch.object(epc,'checked_run',side_effect=AssertionError('must not touch printer')):
            self.assertEqual(epc.step(self.step_args(queue=None)),'All groups printed and dried')

    def test_dry_run_no_submission_and_unverified_execution_refused(self):
        self.build(3)
        args=self.step_args(execute=False)
        with patch.object(epc,'checked_run',side_effect=AssertionError('must not call printer')):
            epc.step(args)
            args=self.step_args(execute=True,tray_loaded=True)
            with self.assertRaisesRegex(ValueError,'托盘通道'):epc.step(args)
        self.assertEqual(epc.read(self.base/'job/state.json')['next_event'],0)

    def test_file_tampering_refused(self):
        self.build(3);(self.base/'job/batch-0001-front.pdf').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'PDF changed'):
            epc.step(self.step_args())

    def test_no_automatic_resend_on_uncertain_outcome(self):
        self.build(3);self.mark_submitted(0)
        state=epc.read(self.base/'job/state.json');state['events'][0]['status']='submission_uncertain';epc.write(self.base/'job/state.json',state)
        with patch.object(epc,'checked_run',side_effect=AssertionError('must not resend')):
            with self.assertRaisesRegex(ValueError,'already submitted'):
                epc.step(self.step_args(execute=True,tray_loaded=True))

    def test_verified_queue_submission_records_one_job(self):
        self.profile.update(transport_verified=True,production_verified=True,
                            queue_name='EPSON_TEST',tray_option='InputSlot',
                            cups_options={'InputSlot':'CD'},verification_evidence=['mock fixture, not hardware evidence'])
        self.build(3)
        calls=[]
        def fake(argv):
            calls.append(argv)
            if argv[0]=='lpoptions':return SimpleNamespace(stdout='InputSlot/Source: Rear *CD\n')
            if argv[0]=='lpstat':return SimpleNamespace(stdout='printer EPSON_TEST is idle. Epson L8058\n')
            return SimpleNamespace(stdout='request id is EPSON_TEST-123 (1 file(s))\n')
        with patch.object(epc,'checked_run',side_effect=fake):epc.step(self.step_args(execute=True,tray_loaded=True))
        self.assertEqual(sum(c[0]=='lp' for c in calls),1)
        state=epc.read(self.base/'job/state.json')
        self.assertEqual(state['next_event'],0)
        self.assertEqual(state['events'][0]['cups_job_id'],'EPSON_TEST-123')
        self.assertEqual(state['events'][0]['status'],'submitted')
        self.assertEqual((state['events'][0]['side'],state['events'][0]['group']),('front',1))

    def test_changed_queue_refused_before_device_access(self):
        self.profile.update(transport_verified=True,production_verified=True,
                            queue_name='OTHER',verification_evidence=['mock'])
        self.build(3)
        with patch.object(epc,'checked_run',side_effect=AssertionError('must not access queue')):
            with self.assertRaisesRegex(ValueError,'exact queue'):
                epc.step(self.step_args(execute=True,tray_loaded=True))

    def test_calibration_job_single_tray_rulers(self):
        m=self.build(calibration=True)
        self.assertTrue(m['calibration'])
        self.assertEqual(len(m['batches']),1)
        self.assertEqual([p['id'] for p in m['batches'][0]['sides']['front']['placements']],['calibration-S1','calibration-S2'])
        ev=[(e['type'],e.get('side')) for e in epc.job_events(m)]
        self.assertEqual(ev,[('side','front'),('dry',None),('side','back'),('dry',None)])

    def test_confirm_dry_rejected_when_no_gate(self):
        self.build(3)
        with self.assertRaisesRegex(ValueError,'No drying gate'):epc.step(self.step_args(confirm_dry=True,queue=None))

    def test_rotation_is_clockwise_without_mirror(self):
        im=Image.new('RGB',(80,40),'white')
        im.paste('red',(0,0,40,20));im.paste('blue',(40,0,80,20))
        im.paste('green',(0,20,40,40));im.paste('yellow',(40,20,80,40))
        path=self.base/'quadrants.png';im.save(path)
        rotated=epc.fitted(path,(40,80),'contain',90)
        self.assertEqual(rotated.getpixel((30,10)),(255,0,0))
        self.assertEqual(rotated.getpixel((10,10)),(0,128,0))
        self.assertEqual(rotated.getpixel((30,70)),(0,0,255))

    def test_calibration_compose_uses_active_file_and_in_place_update(self):
        import numpy as np
        self.profile['transforms']['front']=[1,0,-.5,0,1,.25]
        active=epc.active_profile_path();active.parent.mkdir(parents=True,exist_ok=True)
        epc.write(active,self.profile)
        samples=[{'expected_mm':[x,y],'observed_mm':[1.01*x+.002*y+1,-.003*x+.99*y-1]} for x,y in [(20,50),(120,50),(20,110),(120,110),(70,80)]]
        epc.write(self.base/'samples.json',samples)
        epc.calibrate(argparse.Namespace(samples=self.base/'samples.json',max_residual=.01,reset=False))
        corrected=epc.read(active);a,b,c,d,e,f=corrected['transforms']['front']
        new=np.array([[a,b,c],[d,e,f],[0,0,1]])
        old=np.array([[1,0,-.5],[0,1,.25],[0,0,1]])
        physical=np.array([[1.01,.002,1],[-.003,.99,-1],[0,0,1]])@np.linalg.inv(old)
        self.assertTrue(np.allclose(physical@new,np.eye(3),atol=1e-9))
        self.assertFalse(corrected['production_verified'])

    def test_calibrate_reset_restores_builtin(self):
        active=epc.active_profile_path();active.parent.mkdir(parents=True,exist_ok=True)
        self.profile['transforms']['front']=[1,0,3,0,1,4]
        epc.write(active,self.profile)
        epc.calibrate(argparse.Namespace(samples=None,max_residual=.5,reset=True))
        self.assertEqual(epc.read(active)['transforms']['front'],epc.DEFAULT_PROFILE['transforms']['front'])

    def test_prepare_uses_builtin_when_no_active_file(self):
        os.environ.pop('EPSON_PRINT_CARD_CONFIG_DIR',None)
        os.environ['EPSON_PRINT_CARD_CONFIG_DIR']=str(self.base/'not-created')
        m=self.build(3)
        self.assertEqual(len(m['profile']['slots']),2)
        self.assertEqual(m['profile']['page_mm'],epc.DEFAULT_PROFILE['page_mm'])

    def test_step_outputs_next_step_hints(self):
        import io
        from contextlib import redirect_stdout
        self.profile.update(transport_verified=True,production_verified=True,
                            queue_name='EPSON_TEST',tray_option='InputSlot',
                            cups_options={'InputSlot':'CD'},verification_evidence=['mock fixture, not hardware evidence'])
        self.build(3)
        def fake(argv):
            if argv[0]=='lpoptions':return SimpleNamespace(stdout='InputSlot/Source: Rear *CD\n')
            if argv[0]=='lpstat':return SimpleNamespace(stdout='printer EPSON_TEST is idle. Epson L8058\n')
            return SimpleNamespace(stdout='request id is EPSON_TEST-123 (1 file(s))\n')
        def capture(**kw):
            buf=io.StringIO()
            with patch.object(epc,'checked_run',side_effect=fake):
                with redirect_stdout(buf):epc.step(self.step_args(**kw))
            return buf.getvalue()
        self.assertIn('--execute --tray-loaded',capture())                              # 预览：装盘提示
        self.assertIn('--confirm-output',capture(execute=True,tray_loaded=True))        # 提交后：等出盘
        self.assertIn('装第 2 盘',capture(confirm_output=True,queue=None))               # 确认后：下一盘
        capture(execute=True,tray_loaded=True)
        out=capture(confirm_output=True,queue=None)
        self.assertIn('--confirm-dry',out); self.assertIn('干燥',out)                    # 整面完成：干燥门
        out=capture(confirm_dry=True,queue=None)
        self.assertIn('翻卡',out)                                                        # 干燥放行：翻卡装回
        capture(execute=True,tray_loaded=True)
        capture(confirm_output=True,queue=None)
        capture(execute=True,tray_loaded=True)
        capture(confirm_output=True,queue=None)
        out=capture(confirm_dry=True,queue=None)
        self.assertIn('作业结束',out)                                                     # 全部完成

    def test_queue_list_switch_and_job_update(self):
        import io
        from contextlib import redirect_stdout
        def fake(argv):
            if argv[0]=='lpstat' and '-p' in argv and '-v' not in argv and len(argv)==2:
                return SimpleNamespace(stdout='printer EPSON_L8058 is idle. enabled since x\nprinter OTHER is idle. enabled since x\n')
            if argv[0]=='lpstat' and '-v' in argv:
                return SimpleNamespace(stdout='device for EPSON_L8058: epsonremote://x\ndevice for OTHER: epsonremote://y\n')
            if argv[0]=='lpoptions':
                return SimpleNamespace(stdout='EPIJ_PSrc/Page Setup: *2 3 25\n')
            if argv[0]=='lp':
                return SimpleNamespace(stdout='request id is EPSON_L8058-9 (1 file(s))\n')
            return SimpleNamespace(stdout='')
        with patch.object(epc,'checked_run',side_effect=fake):
            buf=io.StringIO()
            with redirect_stdout(buf): epc.queue_cmd(argparse.Namespace(name=None,job=None))
            out=buf.getvalue()
            self.assertIn('EPSON_L8058',out); self.assertIn('支持',out); self.assertIn('下一步',out)
        # OTHER 未做 lpoptions 区分，改用独立 mock 验证拒绝路径
        def fake2(argv):
            if argv[0]=='lpstat' and len(argv)==2:
                return SimpleNamespace(stdout='printer NOGOOD is idle. enabled since x\n')
            if argv[0]=='lpstat':
                return SimpleNamespace(stdout='device for NOGOOD: ipp://z\n')
            if argv[0]=='lpoptions':
                return SimpleNamespace(stdout='EPIJ_PSrc/Page Setup: *2 3\n')
            return SimpleNamespace(stdout='')
        with patch.object(epc,'checked_run',side_effect=fake2):
            with self.assertRaisesRegex(ValueError,'不支持卡托盘'):
                epc.queue_cmd(argparse.Namespace(name='NOGOOD',job=None))
        # 正常切换：活动 profile 更新 + 作业 manifest 联动 + 审计事件 + 提示
        self.profile.update(transport_verified=True,production_verified=True,verification_evidence=['mock'])
        self.build(3)
        folder=self.base/'job'
        with patch.object(epc,'checked_run',side_effect=fake):
            buf=io.StringIO()
            with redirect_stdout(buf): epc.queue_cmd(argparse.Namespace(name='EPSON_L8058',job=str(folder)))
        out=buf.getvalue()
        self.assertIn('queue_switched',out); self.assertIn('下一步',out)
        self.assertEqual(epc.active_profile()['queue_name'],'EPSON_L8058')
        m=epc.read(folder/'manifest.json')
        self.assertEqual(m['profile']['queue_name'],'EPSON_L8058')
        self.assertEqual(m['profile']['cups_options'].get('PageSize'),'A4.ManuCDR')
        self.assertEqual(m['profile']['cups_options'].get('EPIJ_PSrc'),'25')
        state=epc.read(folder/'state.json')
        self.assertEqual(state['events'][-1]['type'],'queue_switched')
        self.assertEqual(state['manifest_sha256'],epc.digest(folder/'manifest.json'))
        # 换队列后 step 校验通过：换绑已整体接管活动 profile（含验证旗标）
        m=epc.read(folder/'manifest.json')
        self.assertTrue(m['profile']['transport_verified'] and m['profile']['production_verified'])
        with patch.object(epc,'checked_run',side_effect=fake):
            buf=io.StringIO()
            with redirect_stdout(buf): epc.step(self.step_args(queue='EPSON_L8058',execute=True,tray_loaded=True))
        self.assertIn('Submitted',buf.getvalue())

    def test_queue_switch_refused_mid_submission(self):
        self.build(3)
        folder=self.base/'job'; state=epc.read(folder/'state.json')
        state['events'].append({'index':0,'status':'submitted'}); epc.write(folder/'state.json',state)
        def fake(argv):
            if argv[0]=='lpstat' and len(argv)==2:
                return SimpleNamespace(stdout='printer EPSON_L8058 is idle. enabled since x\n')
            if argv[0]=='lpstat':
                return SimpleNamespace(stdout='device for EPSON_L8058: epsonremote://x\n')
            if argv[0]=='lpoptions':
                return SimpleNamespace(stdout='EPIJ_PSrc/Page Setup: *2 3 25\n')
            return SimpleNamespace(stdout='')
        with patch.object(epc,'checked_run',side_effect=fake):
            with self.assertRaisesRegex(ValueError,'先 --confirm-output'):
                epc.queue_cmd(argparse.Namespace(name='EPSON_L8058',job=str(folder)))

    def test_cli_end_to_end_prepare_and_step_preview(self):
        for extra in sorted(self.fronts.iterdir())[3:]:
            (self.fronts/extra.name).unlink()
        out=self.base/'cli-job'
        run=[sys.executable,str(ROOT/'scripts/epson-print-card')]
        env=dict(os.environ,EPSON_PRINT_CARD_CONFIG_DIR=str(self.base/'cli-config'))
        r=subprocess.run(run+['prepare','--front-dir',str(self.fronts),'--back-img',str(self.base/'back.png'),
                              '--group','2x5','--output',str(out),'--dpi','150'],capture_output=True,text=True,env=env)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue((out/'batch-0001-front.pdf').is_file())
        self.assertTrue((out/'batch-0001-back.pdf').is_file())
        self.assertTrue((out/'装卡顺序.html').is_file())
        r=subprocess.run(run+['step','--job',str(out),'--queue','EPSON_TEST'],capture_output=True,text=True,env=env)
        self.assertEqual(r.returncode,0,r.stderr)
        payload=json.loads(r.stdout.splitlines()[0])
        self.assertEqual((payload['side'],payload['group']),('front',1))
        self.assertIn('batch-0001-front.pdf',payload['argv'][-1])
        self.assertIn('--execute --tray-loaded',r.stdout)   # 全自动提示：给出下一步可粘贴命令


    def test_step_without_queue_uses_saved_choice(self):
        store=epc.queue_store_path();store.parent.mkdir(parents=True,exist_ok=True)
        epc.write(store, {'queue': 'EPSON_TEST'})
        self.build(3)
        def fake(argv):
            if argv[:2]==['lpstat','-p']: return SimpleNamespace(stdout='printer EPSON_TEST is idle.  enabled\n')
            if argv[:2]==['lpstat','-v']: return SimpleNamespace(stdout='device for EPSON_TEST: socket://1.2.3.4:9100\n')
            raise AssertionError('preview must not touch printer: '+str(argv))
        with patch.object(epc,'checked_run',side_effect=fake):
            import io, contextlib
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                epc.step(argparse.Namespace(job=str(self.base/'job'),queue=None,execute=False,tray_loaded=False,confirm_output=False,confirm_dry=False))
        self.assertIn('"queue": "EPSON_TEST"',buf.getvalue())


class Sheet(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.dir=self.base/'imgs';self.dir.mkdir()
        for i,color in enumerate(('red','green','blue','yellow','cyan','magenta')):
            Image.new('RGB',(86,54),color).save(self.dir/f'{i:02d}.png')

    def args(self,**kw):
        d=dict(front_dir=str(self.dir),output=str(self.base/'sheet-out'),queue=kw.pop('queue',None),execute=False,columns=kw.pop('columns',None),dpi=150,scale=kw.pop('scale',1.0),rotate=kw.pop('rotate',0))
        d.update(kw);return argparse.Namespace(**d)

    def test_sheet_layout_matches_aspect(self):
        lay=epc.sheet_layout(75,0.628)
        self.assertEqual((lay['columns'],lay['rows'],lay['pages'],lay['capacity']),(9,8,2,72))
        self.assertEqual(epc.sheet_layout(1,0.628)['pages'],1)

    def test_sheet_layout_columns_override(self):
        lay=epc.sheet_layout(6,86/54,columns=2)
        self.assertEqual((lay['columns'],lay['rows'],lay['pages']),(2,5,1))

    def test_sheet_layout_scale_double(self):
        lay=epc.sheet_layout(75,0.628,scale=2)
        self.assertEqual((lay['columns'],lay['rows'],lay['capacity'],lay['pages']),(4,4,16,5))
        self.assertAlmostEqual(lay['cell_mm'][0],210/9*2,places=6)
        self.assertAlmostEqual(lay['cell_mm'][1],297/8*2,places=6)

    def test_fitted_rotates_180(self):
        im=Image.new('RGB',(80,40),'white')
        im.paste('red',(0,0,40,20));im.paste('yellow',(40,20,80,40))
        path=self.base/'half.png';im.save(path)
        r=epc.fitted(path,(80,40),'contain',180)
        self.assertEqual(r.getpixel((5,5)),(255,255,0))
        self.assertEqual(r.getpixel((74,34)),(255,0,0))

    def test_sheet_cells_have_zero_gap(self):
        c0=epc.sheet_cell(0,2,(50,60));c1=epc.sheet_cell(1,2,(50,60));c2=epc.sheet_cell(2,2,(50,60))
        self.assertAlmostEqual(c1[0],c0[0]+c0[2],places=9)
        self.assertAlmostEqual(c2[1],c0[1]+c0[3],places=9)
        self.assertAlmostEqual(c2[0],c0[0],places=9)

    def test_sheet_pdf_pages_size_and_images(self):
        epc.sheet(self.args(columns=2))
        reader=PdfReader(self.base/'sheet-out/sheet.pdf')
        self.assertEqual(len(reader.pages),1)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width)/epc.PT,210,places=3)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.height)/epc.PT,297,places=3)
        self.assertEqual(len(list(reader.pages[0].images)),6)

    def test_sheet_empty_dir_refused(self):
        empty=self.base/'empty';empty.mkdir()
        with self.assertRaisesRegex(ValueError,'No images'):epc.sheet(argparse.Namespace(front_dir=str(empty),output=str(self.base/'x'),queue=None,execute=False,columns=None,dpi=150,scale=1.0,rotate=0))

    def test_sheet_execute_submits_one_job(self):
        calls=[]
        def fake(argv):
            calls.append(argv)
            if argv[0]=='lpstat':return SimpleNamespace(stdout='printer L8058__Remote_ is idle. Epson L8058\n')
            return SimpleNamespace(stdout='request id is L8058__Remote_-77 (1 file(s))\n')
        with patch.object(epc,'checked_run',side_effect=fake):
            epc.sheet(self.args(queue='L8058__Remote_',execute=True))
        lp=[c for c in calls if c[0]=='lp']
        self.assertEqual(len(lp),1)
        self.assertIn('EPIJ_Size=1',lp[0])
        self.assertTrue((self.base/'sheet-out/sheet.pdf').is_file())

    def test_sheet_execute_refuses_disabled_queue(self):
        def fake(argv):
            return SimpleNamespace(stdout='printer L8058__Remote_ is disabled.\n')
        with patch.object(epc,'checked_run',side_effect=fake):
            with self.assertRaisesRegex(ValueError,'disabled'):
                epc.sheet(self.args(queue='L8058__Remote_',execute=True))

    def test_sheet_cli_preview(self):
        r=subprocess.run([sys.executable,str(ROOT/'scripts/epson-print-card'),'sheet','--front-dir',str(self.dir),
                          '--output',str(self.base/'cli-sheet'),'--queue','L8058__Remote_','--dpi','150'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        payload=json.loads(r.stdout)
        self.assertEqual(payload['spacing_mm'],0)
        self.assertFalse(payload['execute'])
        self.assertTrue(payload['argv'][0]=='lp')


PRINTERS_STDOUT = ('printer EPSON_L8058 is idle.  enabled since Sun Sep 27 02:12:50 2026\n'
                   'printer L8058__Remote_ is idle.  enabled since Tue Oct  6 17:14:58 2026\n'
                   'printer typhur_printer01 is idle.  enabled since Thu Sep  3 19:07:32 2026\n')
DEVICES_STDOUT = ('device for EPSON_L8058: socket://192.168.31.38:9100\n'
                  'device for L8058__Remote_: epsonremote://svn5636768prmg%40print.rpt.epson.com.cn\n'
                  'device for typhur_printer01: lpd://10.10.0.30/typhur_printer01\n')


class QueueChoice(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self._old=os.environ.get('EPSON_PRINT_CARD_CONFIG_DIR')
        os.environ['EPSON_PRINT_CARD_CONFIG_DIR']=str(self.base/'config')
        def restore():
            if self._old is None: os.environ.pop('EPSON_PRINT_CARD_CONFIG_DIR',None)
            else: os.environ['EPSON_PRINT_CARD_CONFIG_DIR']=self._old
        self.addCleanup(restore)

    def lpstat_fake(self, argv):
        if argv[:2]==['lpstat','-p']: return SimpleNamespace(stdout=PRINTERS_STDOUT)
        if argv[:2]==['lpstat','-v']: return SimpleNamespace(stdout=DEVICES_STDOUT)
        if argv==['lpstat','-p','L8058__Remote_','-l']: return SimpleNamespace(stdout='printer L8058__Remote_ is idle. Epson\n')
        if argv==['lpstat','-l','-p','L8058__Remote_']: return SimpleNamespace(stdout='Epson L8058\n')
        if argv[0]=='lp': return SimpleNamespace(stdout='request id is L8058__Remote_-31 (1 file(s))\n')
        raise AssertionError('unexpected call: '+str(argv))

    def test_list_printers_parses_names_and_devices(self):
        with patch.object(epc,'checked_run',side_effect=self.lpstat_fake):
            printers={p['name']:p for p in epc.list_printers()}
        self.assertEqual(set(printers),{'EPSON_L8058','L8058__Remote_','typhur_printer01'})
        self.assertTrue(printers['L8058__Remote_']['device'].startswith('epsonremote://'))
        self.assertTrue(printers['EPSON_L8058']['enabled'])

    def test_choose_explicit_saves_then_reused_without_asking(self):
        with patch.object(epc,'checked_run',side_effect=self.lpstat_fake):
            self.assertEqual(epc.choose_queue(explicit='L8058__Remote_'),'L8058__Remote_')
            self.assertEqual(epc.read(epc.queue_store_path())['queue'],'L8058__Remote_')
            self.assertEqual(epc.choose_queue(),'L8058__Remote_')

    def test_choose_explicit_unknown_rejected(self):
        with patch.object(epc,'checked_run',side_effect=self.lpstat_fake):
            with self.assertRaisesRegex(ValueError,'No local printer'):epc.choose_queue(explicit='NOPE')

    def test_choose_multiple_without_tty_gives_guidance(self):
        with patch.object(epc,'checked_run',side_effect=self.lpstat_fake), \
             patch.object(epc.sys.stdin,'isatty',return_value=False):
            with self.assertRaisesRegex(ValueError,'Multiple printers'):epc.choose_queue()

    def test_sheet_execute_without_queue_uses_saved_choice(self):
        store=epc.queue_store_path();store.parent.mkdir(parents=True,exist_ok=True)
        epc.write(store, {'queue':'L8058__Remote_'})
        fronts=self.base/'fronts';fronts.mkdir()
        Image.new('RGB',(86,54),'red').save(fronts/'a.png')
        calls=[]
        def fake(argv):
            calls.append(argv);return self.lpstat_fake(argv)
        with patch.object(epc,'checked_run',side_effect=fake):
            epc.sheet(argparse.Namespace(front_dir=str(fronts),output=str(self.base/'out'),
                                         execute=True,queue=None,columns=None,dpi=150,scale=1.0,rotate=0))
        lp=[c for c in calls if c[0]=='lp']
        self.assertEqual(len(lp),1)
        self.assertIn('L8058__Remote_',lp[0])


if __name__=='__main__':unittest.main()
