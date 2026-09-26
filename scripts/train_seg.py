"""Tier-2 onion instance segmentation student (runs on the phone).

A small U-Net (timm MobileNetV3-Large encoder, Apache-2.0) predicts three
classes per pixel: 0 background, 1 onion interior, 2 onion edge. On the phone,
interior blobs become seeds and grow into interior+edge, so touching onions
stay separate. Labels come from scripts/teacher_masks.py (OWLv2 + SAM) on REAL
photos (Zenodo 10.5281/zenodo.20254934, CC-BY 4.0).

Training-only augmentation: real onion cut-outs pasted onto real photo
backgrounds, with and without the printed calibration mat artwork
(legacy/calibration_mat.png) warped into the scene. Never used for any
reported number.

Split by image-id blocks of 25: block%5==4 holdout (reported), ==0 tune, else train.

Usage: python scripts/train_seg.py --teacher D:/onion/teacher --out apps/web/public/models --epochs 25
"""
import argparse, csv, json, os, random, time, hashlib
from datetime import datetime, timezone
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
import timm
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

p = argparse.ArgumentParser()
p.add_argument('--teacher', required=True)
p.add_argument('--out', default='apps/web/public/models')
p.add_argument('--epochs', type=int, default=25)
p.add_argument('--size', type=int, default=384)
p.add_argument('--mat', default='legacy/calibration_mat.png')
p.add_argument('--limit', type=int, default=0)
a = p.parse_args()
random.seed(26031); np.random.seed(26031); torch.manual_seed(26031)
dev = 'cuda'
S = a.size

rows = [r for r in csv.reader(open(os.path.join(a.teacher, 'index.csv'), encoding='utf8'))]
def blk(name):
    d = ''.join(c for c in name if c.isdigit())
    return (int(d) // 25) % 5 if d else -1
items = [{'name': r[0], 'img': r[1], 'n': int(r[4]), 'b': blk(r[0])} for r in rows if r[0].startswith('Onion')]
train = [i for i in items if i['b'] in (1, 2, 3) and i['n'] > 0]
tune = [i for i in items if i['b'] == 0]
hold = [i for i in items if i['b'] == 4]
if a.limit: train, tune = train[:a.limit], tune[:max(10, a.limit // 10)]
print(f'train {len(train)} tune {len(tune)} holdout {len(hold)}')

MAT = Image.open(a.mat).convert('RGB') if os.path.exists(a.mat) else None

CACHE = {}
def load(it, side=640):
    """Photo + teacher instance map, downsized once and kept in RAM."""
    k = it['name']
    if k not in CACHE:
        img = Image.open(it['img']).convert('RGB')
        inst = Image.open(os.path.join(a.teacher, it['name'] + '.png'))
        s = side / max(inst.size)
        size = (round(inst.width * s), round(inst.height * s))
        CACHE[k] = (np.array(img.resize(size, Image.BILINEAR)), np.array(inst.resize(size, Image.NEAREST)))
    return CACHE[k]

def targets(inst):
    """3-class target: interior = pixels deeper than ~12% of the onion's radius; edge = rest of the onion."""
    y = np.zeros(inst.shape, np.int64)
    y[inst > 0] = 2
    objs = ndi.find_objects(inst)
    for k, sl in enumerate(objs, 1):
        if sl is None: continue
        sl = (slice(max(0, sl[0].start - 1), sl[0].stop + 1), slice(max(0, sl[1].start - 1), sl[1].stop + 1))
        m = inst[sl] == k
        area = m.sum()
        if area < 4: continue
        r = max(1.5, 0.12 * np.sqrt(area / np.pi))
        d = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
        sub = y[sl]; sub[d > r] = 1
    return y

CUTS = []  # (rgb crop, mask crop) of real onions for copy-paste
def harvest(n=600):
    n = min(n, len(train))
    for it in random.sample(train, min(n, len(train))):
        img, inst = load(it)
        for k in np.unique(inst)[1:]:
            m = inst == k
            ys, xs = np.nonzero(m)
            if len(ys) < 400: continue
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            if y0 == 0 or x0 == 0 or y1 == inst.shape[0] or x1 == inst.shape[1]: continue  # skip cut-off onions
            CUTS.append((img[y0:y1, x0:x1].copy(), m[y0:y1, x0:x1].copy()))

def paste_scene():
    """Real background photo + (sometimes) the printed mat + real onion cut-outs."""
    bg_it = random.choice(train)
    bg, _ = load(bg_it)
    H, W = bg.shape[:2]
    canvas = bg.copy()
    # Smear out the background's own onions: use a heavily blurred border-colour fill so only texture remains.
    inst_bg = load(bg_it)[1]
    if inst_bg.any():
        blur = np.array(Image.fromarray(bg).filter(ImageFilter.GaussianBlur(25)))
        mask = ndi.binary_dilation(inst_bg > 0, iterations=8)
        canvas[mask] = blur[mask]
    if MAT is not None and random.random() < 0.7:
        mw = int(W * random.uniform(0.45, 0.9)); mh = int(mw * 210 / 297)
        mat = MAT.resize((mw, mh), Image.BILINEAR).rotate(random.uniform(-25, 25), expand=True, fillcolor=(0, 0, 0))
        mm = np.array(mat); alpha = mm.sum(2) > 0
        # simple lighting: dim and tint the white paper like a photo
        gain = random.uniform(0.7, 1.0); tint = np.array([random.uniform(0.92, 1.0), random.uniform(0.92, 1.0), random.uniform(0.92, 1.05)])
        mm = np.clip(mm * gain * tint, 0, 255).astype(np.uint8)
        ox = random.randint(-mat.width // 4, max(0, W - 3 * mat.width // 4)); oy = random.randint(-mat.height // 4, max(0, H - 3 * mat.height // 4))
        for yy in range(mat.height):
            ty = oy + yy
            if ty < 0 or ty >= H: continue
            xs = np.arange(mat.width); tx = ox + xs
            ok = (tx >= 0) & (tx < W) & alpha[yy]
            canvas[ty, tx[ok]] = mm[yy, xs[ok]]
    inst = np.zeros((H, W), np.uint8)
    n = random.randint(3, 14)
    scale = random.uniform(0.6, 1.3)
    for k in range(1, n + 1):
        rgb, m = random.choice(CUTS)
        h, w = m.shape
        s = scale * random.uniform(0.8, 1.2)
        nh, nw = max(8, int(h * s)), max(8, int(w * s))
        if nh >= H or nw >= W: continue
        rgb = np.array(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR)); m = np.array(Image.fromarray(m.astype(np.uint8) * 255).resize((nw, nh), Image.NEAREST)) > 0
        y0 = random.randint(0, H - nh); x0 = random.randint(0, W - nw)
        region = inst[y0:y0 + nh, x0:x0 + nw]
        if (region[m] > 0).mean() > 0.25: continue  # avoid heavy overlap
        canvas[y0:y0 + nh, x0:x0 + nw][m] = rgb[m]
        region[m] = k
    return canvas, inst

def augment(img, inst):
    H, W = inst.shape
    s = random.uniform(0.7, 1.3) * S / max(H, W)
    nh, nw = max(S, int(H * s)), max(S, int(W * s))
    img = np.array(Image.fromarray(img).resize((nw, nh), Image.BILINEAR)); inst = np.array(Image.fromarray(inst).resize((nw, nh), Image.NEAREST))
    y0 = random.randint(0, nh - S); x0 = random.randint(0, nw - S)
    img = img[y0:y0 + S, x0:x0 + S]; inst = inst[y0:y0 + S, x0:x0 + S]
    k = random.randint(0, 3); img = np.rot90(img, k).copy(); inst = np.rot90(inst, k).copy()
    if random.random() < 0.5: img = img[:, ::-1].copy(); inst = inst[:, ::-1].copy()
    img = img.astype(np.float32)
    img = img * random.uniform(0.6, 1.35) + random.uniform(-20, 20)            # exposure
    img = img * np.array([random.uniform(0.85, 1.15) for _ in range(3)])       # white balance (warm/cool light)
    if random.random() < 0.3: img = np.array(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(random.uniform(0.5, 1.8)))).astype(np.float32)
    img += np.random.normal(0, random.uniform(0, 6), img.shape)
    return np.clip(img, 0, 255).astype(np.uint8), inst

MEAN = np.array([0.485, 0.456, 0.406], np.float32); STD = np.array([0.229, 0.224, 0.225], np.float32)
def to_tensor(img): return torch.from_numpy(((img.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1).copy())

class DS(torch.utils.data.Dataset):
    def __len__(self): return len(train)
    def __getitem__(self, i):
        if CUTS and random.random() < 0.35: img, inst = paste_scene()
        else: img, inst = load(train[i % len(train)])
        img, inst = augment(img, inst)
        return to_tensor(img), torch.from_numpy(targets(inst))

class UNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc = timm.create_model('mobilenetv3_large_100', features_only=True, pretrained=True)
        ch = self.enc.feature_info.channels()  # [16,24,40,112,960]
        def blk(i, o): return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))
        self.d4 = blk(ch[4] + ch[3], 96); self.d3 = blk(96 + ch[2], 64); self.d2 = blk(64 + ch[1], 48); self.d1 = blk(48 + ch[0], 32)
        self.head = nn.Conv2d(32, 3, 1)
    def forward(self, x):
        f = self.enc(x)
        y = f[4]
        for d, skip in ((self.d4, f[3]), (self.d3, f[2]), (self.d2, f[1]), (self.d1, f[0])):
            y = F.interpolate(y, size=skip.shape[-2:], mode='bilinear', align_corners=False)
            y = d(torch.cat([y, skip], 1))
        return F.interpolate(self.head(y), size=x.shape[-2:], mode='bilinear', align_corners=False)

def instances(prob, min_px=60):
    """Seeds = interior blobs; grow into interior+edge by nearest seed (same rule as the phone code)."""
    inter = prob[1] > 0.5
    fg = (prob[1] + prob[2]) > 0.5
    lab, n = ndi.label(inter)
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    for k, sz in enumerate(sizes, 1):
        if sz < min_px: lab[lab == k] = 0
    if lab.max() == 0: return lab, 0
    _, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
    grown = lab[iy, ix] * fg
    return grown, len(np.unique(grown)) - 1

def main():
    harvest()
    print('cut-outs', len(CUTS))
    net = UNet().to(dev)
    dl = torch.utils.data.DataLoader(DS(), batch_size=16, shuffle=True, num_workers=0, drop_last=True)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=a.epochs * len(dl))
    wts = torch.tensor([1.0, 1.0, 2.5], device=dev)  # edges are rare and matter most
    best, best_state = 1e9, None
    t0 = time.time()
    for ep in range(a.epochs):
        net.train()
        for x, y in dl:
            x, y = x.to(dev), y.to(dev)
            with torch.autocast('cuda', dtype=torch.float16):
                loss = F.cross_entropy(net(x), y, weight=wts)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        mae = count_mae(net, tune[:150])
        print(f'epoch {ep + 1} loss {loss.item():.3f} tune count MAE vs teacher {mae:.3f} ({time.time() - t0:.0f}s)', flush=True)
        if mae < best: best, best_state = mae, {k: v.detach().clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    return net

@torch.no_grad()
def predict(net, img):
    net.eval()
    H, W = img.shape[:2]
    s = 512 / max(H, W)
    nh, nw = int(round(H * s / 32) * 32), int(round(W * s / 32) * 32)
    x = to_tensor(np.array(Image.fromarray(img).resize((nw, nh), Image.BILINEAR)))[None].to(dev)
    return torch.softmax(net(x)[0].float(), 0).cpu().numpy()

def count_mae(net, its):
    errs = []
    for it in its:
        img, inst = load(it)
        _, n = instances(predict(net, img))
        errs.append(abs(n - it['n']))
    return float(np.mean(errs)) if errs else 0.0

if __name__ == '__main__':
    net = main()
    os.makedirs(a.out, exist_ok=True)
    net.eval().cpu()
    path = os.path.join(a.out, 'seg.onnx')
    torch.onnx.export(net, torch.zeros(1, 3, 384, 512), path, input_names=['x'], output_names=['logits'],
                      dynamic_axes={'x': {2: 'h', 3: 'w'}, 'logits': {2: 'h', 3: 'w'}}, opset_version=17, dynamo=False)
    torch.save(net.state_dict(), os.path.join(os.path.dirname(a.teacher.rstrip('/')), 'seg_best.pt'))
    sha = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    json.dump({'file': 'seg.onnx', 'side': 512, 'mean': MEAN.tolist(), 'std': STD.tolist(), 'classes': ['bg', 'interior', 'edge'],
               'sha256': sha, 'version': datetime.now(timezone.utc).strftime('%Y%m%d'), 'source': 'scripts/train_seg.py'},
              open(os.path.join(a.out, 'seg.json'), 'w'), indent=1)
    print('exported', path, os.path.getsize(path))
