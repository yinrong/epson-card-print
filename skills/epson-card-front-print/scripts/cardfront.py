#!/usr/bin/env python3
"""Millimetre card composition for front-only (正卡) manual-tray jobs."""
import argparse
import csv
import datetime as dt
import hashlib
import html
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PT = 72 / 25.4
IDENTITY = [1, 0, 0, 0, 1, 0]  # x'=a*x+b*y+c, y'=d*x+e*y+f


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        temp = f.name
    os.replace(temp, path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def num(value, label, low=None):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{label}: finite number required')
    if low is not None and value < low:
        raise ValueError(f'{label}: minimum {low}')
    return value


def point(m, x, y):
    a, b, c, d, e, f = m
    return [a*x+b*y+c, d*x+e*y+f]


def validate(profile):
    width, height = profile['page_mm']
    num(width, 'page width', 1); num(height, 'page height', 1)
    if width > 1000 or height > 1000:
        raise ValueError('Page exceeds 1000 mm')
    slots = profile['slots']
    if not slots or len(slots) > 100:
        raise ValueError('Need 1..100 slots')
    ids = [s['id'] for s in slots]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError('Slot IDs must be unique strings')
    for s in slots:
        for k in ('x', 'y', 'w', 'h'):
            num(s[k], f'{s["id"]}.{k}', 0 if k in ('x', 'y') else .1)
        if s['x']+s['w'] > width or s['y']+s['h'] > height:
            raise ValueError(f'Slot outside page: {s["id"]}')
        if s.get('rotation', 0) not in (0, 90, 180, 270):
            raise ValueError('Slot rotation must be clockwise 0/90/180/270')
        margin = num(profile.get('inset_mm', 3), 'inset', 0)
        if margin*2 >= min(s['w'], s['h']):
            raise ValueError('Inset consumes card')
    for i, s in enumerate(slots):
        for t in slots[i+1:]:
            if min(s['x']+s['w'], t['x']+t['w']) > max(s['x'], t['x']) and min(s['y']+s['h'], t['y']+t['h']) > max(s['y'], t['y']):
                raise ValueError(f'Overlapping slots: {s["id"]}, {t["id"]}')
    mapping = profile.get('back_slot_map', ids)
    if len(mapping) != len(ids) or set(mapping) != set(ids):
        raise ValueError('back_slot_map must be a permutation of slot IDs')
    for i, name in enumerate(mapping):
        t = next(s for s in slots if s['id'] == name)
        if (slots[i]['w'], slots[i]['h']) != (t['w'], t['h']):
            raise ValueError('Back mapping requires matching oriented slot dimensions')
    if not 0 <= num(profile.get('bleed_mm', 0), 'bleed') <= 3:
        raise ValueError('bleed_mm must be 0..3')
    if profile.get('back_rotation', 0) not in (0, 180):
        raise ValueError('back_rotation must be 0 or 180')
    for side in ('front', 'back'):
        m = profile.get('transforms', {}).get(side, IDENTITY)
        if len(m) != 6:
            raise ValueError('Affine transform needs six numbers')
        for v in m:
            num(v, 'transform')
        if m[0]*m[4]-m[1]*m[3] <= 0:
            raise ValueError('Transform must preserve orientation')
        for s in slots:
            for x in (s['x'], s['x']+s['w']):
                for y in (s['y'], s['y']+s['h']):
                    xx, yy = point(m, x, y)
                    if not (-.001 <= xx <= width+.001 and -.001 <= yy <= height+.001):
                        raise ValueError('Calibrated slot falls outside PDF page')
    return profile


def load_cards(path):
    path = Path(path).resolve()
    with path.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    expanded, seen = [], set()
    for row in rows:
        card_id = row.get('id', '').strip()
        if not card_id or card_id in seen:
            raise ValueError('CSV id must be nonempty and unique')
        seen.add(card_id)
        quantity = int(row.get('quantity', '') or 1)
        if not 1 <= quantity <= 10000:
            raise ValueError('quantity must be 1..10000')
        item = {'id': card_id}
        if not row.get('front'):
            raise ValueError(f'{card_id}: missing front image')
        image = (path.parent / row['front']).resolve()
        if not image.is_file():
            raise ValueError(f'Missing image: {image}')
        item['front'] = str(image)
        for copy in range(1, quantity+1):
            expanded.append(dict(item, copy=copy))
    if not expanded:
        raise ValueError('No cards in CSV')
    if len(expanded) > 10000:
        raise ValueError('At most 10000 cards per job')
    return expanded


def fitted(path, size, fit, rotation):
    from PIL import Image, ImageOps
    with Image.open(path) as source:
        source.load()
        im = ImageOps.exif_transpose(source).convert('RGBA')
    background = Image.new('RGBA', im.size, 'white')
    background.alpha_composite(im)
    im = background.convert('RGB').rotate(-rotation, expand=True)
    if fit == 'cover':
        return ImageOps.fit(im, size, method=Image.Resampling.LANCZOS)
    if fit == 'exact':
        return im.resize(size, Image.Resampling.LANCZOS)
    if fit == 'contain':
        scaled = ImageOps.contain(im, size, method=Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', size, 'white')
        canvas.paste(scaled, ((size[0]-scaled.width)//2, (size[1]-scaled.height)//2))
        return canvas
    raise ValueError('fit must be cover or contain')


BLEED = 4


def text(c, x, y, s, size, center=False):
    c.saveState(); c.translate(x, y); c.scale(1, -1); c.setFont('Helvetica-Bold', size)
    (c.drawCentredString if center else c.drawString)(0, -size*.35, s)
    c.restoreState()


def ruler_card(c, slot, side, page_w, page_h):
    """Edge rulers: 0 on the nominal card edge, positive values toward the card centre."""
    x0, y0, w, h = slot['x'], slot['y'], slot['w'], slot['h']
    bx, by = max(0, x0-BLEED), max(0, y0-BLEED)
    clip = c.beginPath(); clip.rect(bx, by, min(page_w, x0+w+BLEED)-bx, min(page_h, y0+h+BLEED)-by)
    c.clipPath(clip, stroke=0)
    c.setStrokeColorRGB(.8, .8, .8); c.setLineWidth(.1)
    for gx in range(-BLEED, int(w)+BLEED+1, 5):
        c.line(x0+gx, y0-BLEED, x0+gx, y0+h+BLEED)
    for gy in range(-BLEED, int(h)+BLEED+1, 5):
        c.line(x0-BLEED, y0+gy, x0+w+BLEED, y0+gy)
    c.setStrokeColorRGB(1, 0, 0); c.setLineWidth(.2); c.rect(x0, y0, w, h)
    c.setStrokeColorRGB(0, 0, 0); c.setFillColorRGB(0, 0, 0)
    cx, cy = x0+w/2, y0+h/2
    # (edge point, inward unit vector, tangent unit vector)
    edges = [((x0, cy), (1, 0), (0, 1)), ((x0+w, cy), (-1, 0), (0, 1)),
             ((cx, y0), (0, 1), (1, 0)), ((cx, y0+h), (0, -1), (1, 0))]
    for (ex, ey), (ix, iy), (tx, ty) in edges:
        for k in range(-2*BLEED, 2*8+1):
            v = k/2
            length = 3 if k % 2 == 0 else 1.5
            px, py = ex+ix*v, ey+iy*v
            c.setLineWidth(.2 if k else .35)
            c.line(px-tx*length, py-ty*length, px+tx*length, py+ty*length)
            if k % 4 == 0 and v != 0:
                text(c, px+tx*(length+1.6), py+ty*(length+1.6), f'{v:g}', 2.2, center=True)
        text(c, ex+ix*.0+tx*5.5, ey+iy*.0+ty*5.5, '0', 2.2, center=True)
    c.setLineWidth(.2)
    c.line(cx-3, cy, cx+3, cy); c.line(cx, cy-3, cx, cy+3)
    text(c, cx, cy-14, f'{slot["id"]} {side.upper()}', 4, center=True)
    text(c, cx, cy+14, 'PAGE TOP ^', 3, center=True)
    c.line(cx, cy+20, cx, cy+28); c.line(cx, cy+20, cx-2, cy+23); c.line(cx, cy+20, cx+2, cy+23)


def make_pdf(path, profile, placements, side, dpi, fit, calibration=False):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    width, height = profile['page_mm']
    c = canvas.Canvas(str(path), pagesize=(width*PT, height*PT), pageCompression=1)
    c.setTitle(f'{profile["name"]} {side}')
    c.translate(0, height*PT)
    c.scale(PT, -PT)
    a, b, cc, d, e, f = profile.get('transforms', {}).get(side, IDENTITY)
    c.transform(a, d, b, e, cc, f)
    # Negative effective inset = bleed beyond the card edge, hiding residual placement error.
    inset = profile.get('inset_mm', 3) - profile.get('bleed_mm', 0)
    for placement in placements:
        slot = placement['slot']
        x, y = slot['x']+inset, slot['y']+inset
        w, h = slot['w']-2*inset, slot['h']-2*inset
        c.saveState()
        if calibration:
            ruler_card(c, slot, side, width, height)
            c.restoreState()
            continue
        clip = c.beginPath(); clip.rect(x, y, w, h); c.clipPath(clip, stroke=0)
        rotation = slot.get('rotation', 0)
        pixels = (max(1,round(w*dpi/25.4)), max(1,round(h*dpi/25.4)))
        if fit == 'exact':
            # Card art at 1:1 inside the nominal card area; bleed repeats the edge pixels outward.
            bleed = profile.get('bleed_mm', 0)
            b = round(bleed*dpi/25.4)
            core = fitted(placement['card']['front'], (pixels[0]-2*b, pixels[1]-2*b), fit, rotation)
            from PIL import Image
            import numpy as np
            im = Image.fromarray(np.pad(np.asarray(core), ((b, b), (b, b), (0, 0)), mode='edge'))
        else:
            im = fitted(placement['card']['front'], pixels, fit, rotation)
        c.translate(x, y+h); c.scale(1,-1)
        c.drawImage(ImageReader(im),0,0,width=w,height=h)
        c.restoreState()
    c.showPage(); c.save()


def prepare(args):
    profile = validate(read(args.profile))
    cards = load_cards(args.cards) if not args.calibration else [dict(id='calibration-'+s['id'], copy=1) for s in profile['slots']]
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Manifest appears only after every file is complete. Failed folders are not runnable.
    capacity = len(profile['slots'])
    manifest = {'schema':1,'mode':'front-only','profile':profile,'calibration':args.calibration,
                'created_at':dt.datetime.now().astimezone().isoformat(),'cards':len(cards),'batches':[]}
    manifest['runtime']={'python':sys.version.split()[0],**{name:importlib.metadata.version(name) for name in ('Pillow','reportlab')}}
    for start in range(0,len(cards),capacity):
        batch_num = start//capacity+1
        batch = {'number':batch_num,'cards':cards[start:start+capacity],'sides':{}}
        placements = [{'card':card,'slot':profile['slots'][i]} for i,card in enumerate(batch['cards'])]
        filename = f'batch-{batch_num:04d}-front.pdf'
        path = output/filename
        make_pdf(path,profile,placements,'front',args.dpi,args.fit,args.calibration)
        batch['sides']['front'] = {'file':filename,'sha256':digest(path),'placements':[{'id':p['card']['id'],'copy':p['card']['copy'],'slot':p['slot']['id']} for p in placements]}
        manifest['batches'].append(batch)
    write(output/'manifest.json',manifest)
    write(output/'state.json',{'manifest_sha256':digest(output/'manifest.json'),'next_event':0,'events':[]})
    lines = ['<!doctype html><meta charset="utf-8"><title>Card loading plan</title><style>body{font:16px system-ui;max-width:960px;margin:32px auto}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}}</style>',
             '<h1>逐盘正卡打印（仅正面）</h1><p>每盘顺序：装卡 → 提交正面 → 确认出盘 → 下一盘。不翻卡、不打印背面。保持托架进机方向一致。图像按正常阅读方向提供，程序不镜像文字。</p>']
    for b in manifest['batches']:
        lines.append(f'<h2>第 {b["number"]} 盘</h2><table><tr><th>卡号</th><th>份数序号</th><th>槽位</th></tr>')
        for placement in b['sides']['front']['placements']:
            lines.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in (placement['id'],placement['copy'],placement['slot']))+'</tr>')
        lines.append('</table>')
        name = b['sides']['front']['file']
        lines.append(f'<p><a href="{name}">{name}</a></p>')
    (output/'装卡顺序.html').write_text('\n'.join(lines))
    print(json.dumps({'output':str(output),'cards':len(cards),'batches':len(manifest['batches']),'mode':'front-only','physical_verified':False},ensure_ascii=False))


def calibrate(args):
    import numpy as np
    profile = validate(read(args.profile))
    samples = read(args.samples)
    if len(samples) < 4:
        raise ValueError('Use at least four measured points, spread across all slots')
    expected = np.array([s['expected_mm'] for s in samples], dtype=float)
    observed = np.array([s['observed_mm'] for s in samples], dtype=float)
    if expected.shape != observed.shape or expected.shape[1:] != (2,) or not np.isfinite(expected).all() or not np.isfinite(observed).all():
        raise ValueError('Each sample needs two finite expected and observed coordinates')
    design = np.column_stack((expected, np.ones(len(samples))))
    coeff,resid,rank,sv = np.linalg.lstsq(design,observed,rcond=None)
    if rank != 3 or np.linalg.cond(design) > 1e6:
        raise ValueError('Calibration points are collinear or poorly spread')
    forward = np.array([[coeff[0,0],coeff[1,0],coeff[2,0]],[coeff[0,1],coeff[1,1],coeff[2,1]],[0,0,1]])
    if np.linalg.det(forward[:2,:2]) <= 0:
        raise ValueError('Reflected observations: check point IDs and orientation')
    error = np.linalg.norm(design@coeff-observed,axis=1)
    if max(error) > args.max_residual:
        raise ValueError(f'Measurements inconsistent; residual {max(error):.3f} mm')
    # Observations of an already corrected profile require composing old correction.
    old = profile.get('transforms',{}).get('front',IDENTITY)
    old_matrix = np.array([[old[0],old[1],old[2]],[old[3],old[4],old[5]],[0,0,1]])
    correction = old_matrix @ np.linalg.inv(forward)
    m = list(correction[0])+list(correction[1])
    profile.setdefault('transforms',{})['front'] = m
    profile.setdefault('calibration_records',{})['front'] = {'samples':samples,'max_residual_mm':float(max(error)),'status':'computed_pending_repeat_print'}
    # A newly computed correction has not been verified by a repeat print.
    profile['production_verified'] = False
    validate(profile)
    if Path(args.output).exists():
        raise ValueError('Choose a new output profile path')
    write(args.output,profile)
    print(json.dumps({'transform':m,'max_residual_mm':float(max(error)),'production_verified':False}))


def checked_run(argv):
    return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=20,env=dict(os.environ,LC_ALL='C',LANG='C'))


def command(profile, queue, pdf):
    if not queue or queue.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_.-]+',queue):
        raise ValueError('Use an explicit local CUPS queue name')
    options = profile.get('cups_options',{})
    forbidden = {'copies','sides','number-up','fit-to-page','scaling','print-scaling','page-ranges','outputorder','job-sheets','orientation-requested','mirror'}
    for key,val in options.items():
        if key.lower() in forbidden or not re.fullmatch(r'[A-Za-z0-9_.-]+',key) or not re.fullmatch(r'[A-Za-z0-9_.,() -]*',str(val)):
            raise ValueError(f'Unsupported option: {key}')
    cmd = ['lp','-d',queue,'-n','1','-o','sides=one-sided','-o','number-up=1','-o','print-scaling=none','-o','fit-to-page=false','-o','job-sheets=none','-o','outputorder=normal']
    for key,val in sorted(options.items()):
        val = str(val)
        cmd += ['-o',f'{key}="{val}"' if ' ' in val or not val else f'{key}={val}']
    return cmd+['--',str(pdf)]


def next_event(manifest, state):
    index = state['next_event']
    if index >= len(manifest['batches']):
        return None
    return manifest['batches'][index], 'front'


def step(args):
    folder = Path(args.job).resolve()
    lock = folder/'.state.lock'
    import fcntl
    with lock.open('a') as lockfile:
        fcntl.flock(lockfile,fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest,state = read(folder/'manifest.json'),read(folder/'state.json')
        if state['manifest_sha256'] != digest(folder/'manifest.json'):
            raise ValueError('Manifest changed; create a new job')
        event = next_event(manifest,state)
        if event is None:
            print('All fronts manually confirmed'); return 'All fronts manually confirmed'
        batch,side = event
        spec = batch['sides'][side]; pdf=folder/spec['file']
        if digest(pdf) != spec['sha256']:
            raise ValueError('PDF changed; create a new job')
        pending = state['events'][-1] if state['events'] and state['events'][-1]['index']==state['next_event'] else None
        if args.confirm_output:
            if not pending or pending['status'] not in ('submitted','submission_uncertain'):
                raise ValueError('No submitted side to confirm')
            pending['status']='operator_confirmed'; pending['confirmed_at']=dt.datetime.now().astimezone().isoformat()
            state['next_event'] += 1; write(folder/'state.json',state)
            print(f'Confirmed batch {batch["number"]} front; use step again after loading the next tray'); return
        if pending:
            raise ValueError('Side already submitted or outcome uncertain; inspect printer/CUPS and confirm output. No automatic resend.')
        profile = validate(manifest['profile'])
        cmd = command(profile,args.queue,pdf)
        print(json.dumps({'batch':batch['number'],'side':side,'placements':spec['placements'],'argv':cmd,'execute':args.execute},ensure_ascii=False))
        if not args.execute:
            return
        if not args.tray_loaded:
            raise ValueError('Load the specified tray, then pass --tray-loaded')
        if not profile.get('transport_verified'):
            raise ValueError('Tray transport/options not verified for this profile')
        if not manifest['calibration'] and not profile.get('production_verified'):
            raise ValueError('Production profile needs repeat-print evidence; calibration jobs remain available')
        if not profile.get('verification_evidence'):
            raise ValueError('Profile must record transport/print evidence')
        if profile.get('queue_name') != args.queue:
            raise ValueError('Profile must be calibrated for this exact queue_name')
        tray_option = profile.get('tray_option')
        if not tray_option or tray_option not in profile.get('cups_options',{}):
            raise ValueError('Profile must select its verified tray source option')
        capabilities = checked_run(['lpoptions','-p',args.queue,'-l']).stdout
        choices = {}
        for line in capabilities.splitlines():
            if ':' in line:
                key, values = line.split(':',1)
                choices[key.split('/')[0]] = {v.lstrip('*') for v in values.split()}
        for key,val in profile['cups_options'].items():
            if key in choices and str(val) not in choices[key]:
                raise ValueError(f'Queue does not advertise selected option {key}={val}')
        info = checked_run(['lpstat','-p',args.queue,'-l']).stdout
        if 'disabled' in info.lower():
            raise ValueError('Target queue disabled')
        model = checked_run(['lpstat','-l','-p',args.queue]).stdout
        ppd=Path('/etc/cups/ppd')/(args.queue+'.ppd')
        if ppd.is_file():
            model += ppd.read_text(errors='replace')
        if not re.search(r'epson|L805[08]',model,re.I):
            raise ValueError('Cannot identify target as Epson; inspect queue before submitting')
        pending={'index':state['next_event'],'batch':batch['number'],'side':side,'status':'submission_uncertain','started_at':dt.datetime.now().astimezone().isoformat()}
        state['events'].append(pending);write(folder/'state.json',state)
        result=checked_run(cmd)  # An error deliberately leaves an uncertain state.
        match=re.search(r'request id is (\S+)',result.stdout)
        pending.update(status='submitted',cups_job_id=match.group(1) if match else None)
        write(folder/'state.json',state)
        print('Submitted one front; confirm physical output before advancing')


def parser():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('prepare');b.add_argument('--profile',required=True);b.add_argument('--cards');b.add_argument('--output',required=True)
    b.add_argument('--calibration',action='store_true');b.add_argument('--dpi',type=int,choices=(150,300,600),default=300);b.add_argument('--fit',choices=('cover','contain','exact'),default='contain');b.set_defaults(func=prepare)
    c=sub.add_parser('calibrate');c.add_argument('--profile',required=True);c.add_argument('--samples',required=True);c.add_argument('--output',required=True);c.add_argument('--max-residual',type=float,default=.5);c.set_defaults(func=calibrate)
    s=sub.add_parser('step');s.add_argument('--job',required=True);s.add_argument('--queue');s.add_argument('--execute',action='store_true');s.add_argument('--tray-loaded',action='store_true');s.add_argument('--confirm-output',action='store_true');s.set_defaults(func=step)
    return p


def main():
    args=parser().parse_args()
    if args.cmd=='prepare' and not args.calibration and not args.cards:
        raise ValueError('--cards required except for calibration')
    args.func(args)


if __name__=='__main__':
    try:
        main()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr);sys.exit(2)
