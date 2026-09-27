import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
cp=module('cardprint')


class Cards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.profile=cp.read(ROOT/'profiles/l8058-stock-provisional.json')
        for i,color in enumerate(('red','green','blue','yellow','cyan','magenta')):
            Image.new('RGB',(86,54),color).save(self.base/f'{i}.png')
        (self.base/'cards.csv').write_text('id,front,back,quantity\nA,0.png,1.png,1\nB,2.png,3.png,1\nC,4.png,5.png,1\n')

    def build(self, profile=None, calibration=False):
        cp.write(self.base/'profile.json',profile or self.profile)
        args=argparse.Namespace(profile=str(self.base/'profile.json'),cards=str(self.base/'cards.csv'),output=str(self.base/'job'),calibration=calibration,dpi=150,fit='contain')
        cp.prepare(args)
        return cp.read(self.base/'job/manifest.json')

    def test_partial_batch_pairing_and_back_permutation(self):
        self.profile['back_slot_map']=['S2','S1']
        m=self.build()
        self.assertEqual(len(m['batches']),2)
        self.assertEqual(m['batches'][0]['sides']['back']['placements'],[{'id':'A','copy':1,'slot':'S2'},{'id':'B','copy':1,'slot':'S1'}])
        self.assertEqual(m['batches'][1]['sides']['back']['placements'],[{'id':'C','copy':1,'slot':'S2'}])
        for b in m['batches']:
            for s in b['sides'].values():
                reader=PdfReader(self.base/'job'/s['file'])
                self.assertEqual(len(reader.pages),1)
                self.assertAlmostEqual(float(reader.pages[0].mediabox.width)/cp.PT,self.profile['page_mm'][0],places=4)
                self.assertAlmostEqual(float(reader.pages[0].mediabox.height)/cp.PT,self.profile['page_mm'][1],places=4)

    def test_invalid_overlap_and_back_map(self):
        profile=copy.deepcopy(self.profile);profile['slots'][1]['x']=11
        with self.assertRaises(ValueError):cp.validate(profile)
        profile=copy.deepcopy(self.profile);profile['back_slot_map']=['S1','S1']
        with self.assertRaises(ValueError):cp.validate(profile)

    def test_rotation_is_clockwise_without_mirror(self):
        im=Image.new('RGB',(80,40),'white')
        im.paste('red',(0,0,40,20));im.paste('blue',(40,0,80,20))
        im.paste('green',(0,20,40,40));im.paste('yellow',(40,20,80,40))
        path=self.base/'quadrants.png';im.save(path)
        rotated=cp.fitted(path,(40,80),'contain',90)
        self.assertEqual(rotated.getpixel((30,10)),(255,0,0))
        self.assertEqual(rotated.getpixel((10,10)),(0,128,0))
        self.assertEqual(rotated.getpixel((30,70)),(0,0,255))

    def test_translation_calibration_composes_existing_transform(self):
        import numpy as np
        self.profile['transforms']['front']=[1,0,-.5,0,1,.25]
        cp.write(self.base/'profile.json',self.profile)
        samples=[{'expected_mm':[x,y],'observed_mm':[1.01*x+.002*y+1,-.003*x+.99*y-1]} for x,y in [(20,50),(120,50),(20,110),(120,110),(70,80)]]
        cp.write(self.base/'samples.json',samples)
        cp.calibrate(argparse.Namespace(profile=self.base/'profile.json',samples=self.base/'samples.json',side='front',output=self.base/'corrected.json',max_residual=.01))
        corrected=cp.read(self.base/'corrected.json');a,b,c,d,e,f=corrected['transforms']['front']
        new=np.array([[a,b,c],[d,e,f],[0,0,1]])
        old=np.array([[1,0,-.5],[0,1,.25],[0,0,1]])
        physical=np.array([[1.01,.002,1],[-.003,.99,-1],[0,0,1]])@np.linalg.inv(old)
        self.assertTrue(np.allclose(physical@new,np.eye(3),atol=1e-9))
        self.assertFalse(corrected['production_verified'])

    def test_dry_run_no_submission_and_unverified_execution_refused(self):
        self.build()
        args=argparse.Namespace(job=self.base/'job',queue='EPSON_TEST',execute=False,tray_loaded=False,confirm_output=False)
        with patch.object(cp,'checked_run',side_effect=AssertionError('must not call printer')):
            cp.step(args)
            args.execute=True;args.tray_loaded=True
            with self.assertRaisesRegex(ValueError,'transport'):cp.step(args)
        self.assertEqual(cp.read(self.base/'job/state.json')['next_event'],0)

    def test_file_tampering_refused(self):
        self.build();(self.base/'job/batch-0001-front.pdf').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'PDF changed'):
            cp.step(argparse.Namespace(job=self.base/'job',queue='EPSON_TEST',execute=False,tray_loaded=False,confirm_output=False))

    def test_confirmation_advances_only_one_side(self):
        self.build();folder=self.base/'job';state=cp.read(folder/'state.json')
        state['events']=[{'index':0,'status':'submitted'}];cp.write(folder/'state.json',state)
        args=argparse.Namespace(job=folder,queue=None,execute=False,tray_loaded=False,confirm_output=True)
        cp.step(args)
        state=cp.read(folder/'state.json');self.assertEqual(state['next_event'],1)
        with self.assertRaisesRegex(ValueError,'No submitted'):cp.step(args)

    def test_no_automatic_resend_on_uncertain_outcome(self):
        self.build();folder=self.base/'job';state=cp.read(folder/'state.json')
        state['events']=[{'index':0,'status':'submission_uncertain'}];cp.write(folder/'state.json',state)
        with patch.object(cp,'checked_run',side_effect=AssertionError('must not resend')):
            with self.assertRaisesRegex(ValueError,'already submitted'):
                cp.step(argparse.Namespace(job=folder,queue='EPSON_TEST',execute=True,tray_loaded=True,confirm_output=False))

    def test_verified_queue_submission_records_one_job(self):
        self.profile.update(transport_verified=True,production_verified=True,
                            queue_name='EPSON_TEST',tray_option='InputSlot',
                            cups_options={'InputSlot':'CD'},verification_evidence=['mock fixture, not hardware evidence'])
        self.build()
        calls=[]
        def fake(argv):
            calls.append(argv)
            if argv[0]=='lpoptions':return SimpleNamespace(stdout='InputSlot/Source: Rear *CD\n')
            if argv[0]=='lpstat':return SimpleNamespace(stdout='printer EPSON_TEST is idle. Epson L8058\n')
            return SimpleNamespace(stdout='request id is EPSON_TEST-123 (1 file(s))\n')
        args=argparse.Namespace(job=self.base/'job',queue='EPSON_TEST',execute=True,tray_loaded=True,confirm_output=False)
        with patch.object(cp,'checked_run',side_effect=fake):cp.step(args)
        self.assertEqual(sum(c[0]=='lp' for c in calls),1)
        state=cp.read(self.base/'job/state.json')
        self.assertEqual(state['next_event'],0)
        self.assertEqual(state['events'][0]['cups_job_id'],'EPSON_TEST-123')
        self.assertEqual(state['events'][0]['status'],'submitted')

    def test_changed_queue_refused_before_device_access(self):
        self.profile.update(transport_verified=True,production_verified=True,
                            queue_name='OTHER',verification_evidence=['mock'])
        self.build()
        with patch.object(cp,'checked_run',side_effect=AssertionError('must not access queue')):
            with self.assertRaisesRegex(ValueError,'exact queue'):
                cp.step(argparse.Namespace(job=self.base/'job',queue='EPSON_TEST',execute=True,tray_loaded=True,confirm_output=False))

    def test_csv_quantity_duplicate_and_missing_back(self):
        path=self.base/'cards.csv';path.write_text('id,front,back,quantity\nA,0.png,1.png,3\n')
        rows=cp.load_cards(path);self.assertEqual([r['copy'] for r in rows],[1,2,3])
        path.write_text('id,front,back\nA,0.png,1.png\nA,2.png,3.png\n')
        with self.assertRaises(ValueError):cp.load_cards(path)
        path.write_text('id,front,back\nA,0.png,\n')
        with self.assertRaises(ValueError):cp.load_cards(path)


if __name__=='__main__':unittest.main()
