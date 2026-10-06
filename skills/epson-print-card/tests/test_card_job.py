import argparse
import copy
import importlib.util
import json
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
        self.profile=epc.read(ROOT/'profiles/l8058-stock-provisional.json')
        self.fronts=self.base/'fronts';self.fronts.mkdir()
        for i,color in enumerate(('red','green','blue','yellow','cyan','magenta','orange','purple','brown','pink','gray')):
            Image.new('RGB',(86,54),color).save(self.fronts/f'{i:02d}-card.png')
        Image.new('RGB',(86,54),'white').save(self.base/'back.png')

    def build(self, front_count=3, group='2x5', profile=None, calibration=False):
        for extra in sorted(self.fronts.iterdir())[front_count:]:
            (self.fronts/extra.name).unlink()
        profile_path=self.base/'profile.json'
        epc.write(profile_path,profile or self.profile)
        args=argparse.Namespace(profile=str(self.base/'profile.json'),
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
            with self.assertRaisesRegex(ValueError,'transport'):epc.step(args)
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

    def test_translation_calibration_composes_existing_transform(self):
        import numpy as np
        self.profile['transforms']['front']=[1,0,-.5,0,1,.25]
        epc.write(self.base/'profile.json',self.profile)
        samples=[{'expected_mm':[x,y],'observed_mm':[1.01*x+.002*y+1,-.003*x+.99*y-1]} for x,y in [(20,50),(120,50),(20,110),(120,110),(70,80)]]
        epc.write(self.base/'samples.json',samples)
        epc.calibrate(argparse.Namespace(profile=self.base/'profile.json',samples=self.base/'samples.json',output=self.base/'corrected.json',max_residual=.01))
        corrected=epc.read(self.base/'corrected.json');a,b,c,d,e,f=corrected['transforms']['front']
        new=np.array([[a,b,c],[d,e,f],[0,0,1]])
        old=np.array([[1,0,-.5],[0,1,.25],[0,0,1]])
        physical=np.array([[1.01,.002,1],[-.003,.99,-1],[0,0,1]])@np.linalg.inv(old)
        self.assertTrue(np.allclose(physical@new,np.eye(3),atol=1e-9))
        self.assertFalse(corrected['production_verified'])

    def test_cli_end_to_end_prepare_and_step_preview(self):
        for extra in sorted(self.fronts.iterdir())[3:]:
            (self.fronts/extra.name).unlink()
        out=self.base/'cli-job'
        run=[sys.executable,str(ROOT/'scripts/epson-print-card')]
        r=subprocess.run(run+['prepare','--profile',str(ROOT/'profiles/l8058-stock-provisional.json'),
                              '--front-dir',str(self.fronts),'--back-img',str(self.base/'back.png'),
                              '--group','2x5','--output',str(out),'--dpi','150'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue((out/'batch-0001-front.pdf').is_file())
        self.assertTrue((out/'batch-0001-back.pdf').is_file())
        self.assertTrue((out/'装卡顺序.html').is_file())
        r=subprocess.run(run+['step','--job',str(out),'--queue','EPSON_TEST'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        payload=json.loads(r.stdout)
        self.assertEqual((payload['side'],payload['group']),('front',1))
        self.assertIn('batch-0001-front.pdf',payload['argv'][-1])


if __name__=='__main__':unittest.main()
