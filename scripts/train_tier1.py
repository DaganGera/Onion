"""Tier-1: a small learned cross-check for Tier-0.

Trains MobileNetV3-Small (torchvision, BSD-3) on bulb crops cut by the Tier-0
segmentation from REAL photos (Zenodo 10.5281/zenodo.20254934, CC-BY 4.0).
Training uses only single-bulb photos, where the folder label is exactly the
bulb's label. Nothing synthetic, no copy-paste.

Splits follow tools/eval_zenodo.ts: blocks of 25 consecutive image ids;
block % 5 == 0 -> tune (threshold, early stopping), == 4 -> holdout (reported),
1..3 -> train.

Usage:
  python scripts/train_tier1.py --crops D:/onion/crops --out apps/web/public/models
Writes reports/zenodo_tier1.json and <out>/tier1.onnx (+ tier1.int8.onnx if quantisation holds up).
"""
import argparse, csv, glob, json, os, random, time
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

p = argparse.ArgumentParser()
p.add_argument('--crops', required=True)
p.add_argument('--out', default='apps/web/public/models')
p.add_argument('--epochs', type=int, default=10)
p.add_argument('--size', type=int, default=128)
p.add_argument('--seed', type=int, default=26031)
a = p.parse_args()
random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
dev = 'cuda' if torch.cuda.is_available() else 'cpu'

rows = []
for f in sorted(glob.glob(os.path.join(a.crops, 'crops_*.csv'))):
    with open(f, newline='') as fh:
        rows += list(csv.DictReader(fh))
for r in rows:
    r['label'] = int(r['label']); r['image_id'] = int(r['image_id'])
train = [r for r in rows if r['split'] == 'train' and r['qty'] == 'single']
tune = [r for r in rows if r['split'] == 'tune']
hold = [r for r in rows if r['split'] == 'holdout']
print(f'crops: train {len(train)} tune {len(tune)} holdout {len(hold)} device {dev}')

MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
aug = transforms.Compose([
    transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(),
    transforms.RandomApply([transforms.RandomRotation(30)], p=0.5),
    transforms.RandomResizedCrop(a.size, scale=(0.8, 1.0), ratio=(0.9, 1.1)),
    transforms.ColorJitter(brightness=0.25, contrast=0.2, saturation=0.1, hue=0.0),  # keep hue: it carries the defect signal
    transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
plain = transforms.Compose([transforms.Resize(a.size), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])

class DS(Dataset):
    def __init__(s, rs, tf): s.rs, s.tf = rs, tf
    def __len__(s): return len(s.rs)
    def __getitem__(s, i):
        r = s.rs[i]
        return s.tf(Image.open(os.path.join(a.crops, 'img', r['file'])).convert('RGB')), r['label']

w = [1.0 / sum(1 for x in train if x['label'] == r['label']) for r in train]
dl = DataLoader(DS(train, aug), batch_size=64, sampler=WeightedRandomSampler(w, len(train), replacement=True), num_workers=0)

net = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
net.classifier[3] = nn.Linear(net.classifier[3].in_features, 2)
net.to(dev)
opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs * len(dl))
lossf = nn.CrossEntropyLoss()

@torch.no_grad()
def predict(rs):
    net.eval()
    out = []
    for i in range(0, len(rs), 256):
        x = torch.stack([plain(Image.open(os.path.join(a.crops, 'img', r['file'])).convert('RGB')) for r in rs[i:i + 256]]).to(dev)
        out += torch.softmax(net(x), 1)[:, 1].cpu().tolist()
    return out

def auc(y, s):
    pos = [b for a_, b in zip(y, s) if a_ == 1]; neg = [b for a_, b in zip(y, s) if a_ == 0]
    if not pos or not neg: return float('nan')
    s_ = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    # Mann-Whitney with average ranks
    ranks, i = {}, 0
    vals = [v for v, _ in s_]
    rsum = 0.0
    while i < len(s_):
        j = i
        while j + 1 < len(s_) and vals[j + 1] == vals[i]: j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            if s_[k][1] == 1: rsum += avg
        i = j + 1
    return (rsum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

def image_scores(rs, ps):
    """Image score = max bulb probability (same rule as the Tier-0 image score)."""
    m = {}
    for r, pr in zip(rs, ps):
        k = r['image_id']
        m[k] = max(m.get(k, (0, r))[0], pr), r
    return m

best, best_state = -1, None
t0 = time.time()
tune_single = [r for r in tune if r['qty'] == 'single']
for ep in range(a.epochs):
    net.train()
    for x, y in dl:
        x, y = x.to(dev), y.to(dev)
        opt.zero_grad(); l = lossf(net(x), y); l.backward(); opt.step(); sched.step()
    au = auc([r['label'] for r in tune_single], predict(tune_single))
    print(f'epoch {ep + 1}: tune single-crop AUC {au:.3f} ({time.time() - t0:.0f}s)')
    if au > best: best, best_state = au, {k: v.detach().clone() for k, v in net.state_dict().items()}
net.load_state_dict(best_state)

def youden(y, s):
    best = (0.5, -1)
    for t in sorted(set(s)):
        tp = sum(1 for a_, b in zip(y, s) if a_ == 1 and b >= t); P = sum(y)
        tn = sum(1 for a_, b in zip(y, s) if a_ == 0 and b < t); N = len(y) - P
        j = tp / P + tn / N - 1
        if j > best[1]: best = (t, j)
    return best[0]

def metrics(y, s, thr):
    tp = sum(1 for a_, b in zip(y, s) if a_ == 1 and b >= thr); P = sum(y)
    tn = sum(1 for a_, b in zip(y, s) if a_ == 0 and b < thr); N = len(y) - P
    return {'auc': round(auc(y, s), 3), 'n_unhealthy': P, 'n_healthy': N, 'sensitivity': round(tp / P, 3), 'specificity': round(tn / N, 3), 'accuracy': round((tp + tn) / (P + N), 3)}

tune_img = image_scores(tune, predict(tune))
thr = youden([r['label'] for _, r in tune_img.values()], [s for s, _ in tune_img.values()])
hold_p = predict(hold)
hold_img = image_scores(hold, hold_p)
def sub(f):
    items = [(s, r) for s, r in hold_img.values() if f(r)]
    return metrics([r['label'] for _, r in items], [s for s, _ in items], thr)

# Same image ids as the Tier-0 report, for a like-for-like comparison.
same = {}
t0_path = 'reports/zenodo_tier0.json'
if os.path.exists(t0_path):
    t0r = json.load(open(t0_path))
    t0s = {h['id']: h for h in t0r.get('holdout_ids', [])}
    items = [(s, r) for k, (s, r) in hold_img.items() if k in t0s]
    if items:
        y = [r['label'] for _, r in items]
        same = {'n_images': len(items), 'tier1': metrics(y, [s for s, _ in items], thr),
                'tier0': metrics(y, [t0s[r['image_id']]['score'] for _, r in items], t0r['threshold_from_tune']),
                'tier0_images_without_tier1_crop': len(t0s) - len(items)}

os.makedirs(a.out, exist_ok=True)
net.eval().cpu()
onnx_path = os.path.join(a.out, 'tier1.onnx')
torch.onnx.export(net, torch.zeros(1, 3, a.size, a.size), onnx_path, input_names=['x'], output_names=['logits'],
                  dynamic_axes={'x': {0: 'n'}, 'logits': {0: 'n'}}, opset_version=17, dynamo=False)
report = {
    'generatedBy': 'scripts/train_tier1.py', 'at': datetime.now(timezone.utc).isoformat(),
    'model': 'MobileNetV3-Small (torchvision, ImageNet init), 2-class healthy/unhealthy bulb crop, input %d px' % a.size,
    'data': 'Zenodo 10.5281/zenodo.20254934 (CC-BY 4.0) bulb crops cut by Tier-0; train = single-bulb photos in blocks 1-3',
    'n_train_crops': len(train), 'n_tune_crops': len(tune), 'n_holdout_crops': len(hold),
    'best_tune_single_crop_auc': round(best, 3), 'image_threshold_from_tune': round(thr, 4),
    'holdout_image_level': {'all': sub(lambda r: True), 'red': sub(lambda r: r['variety'] == 'red'), 'white': sub(lambda r: r['variety'] == 'white'),
                            'single': sub(lambda r: r['qty'] == 'single'), 'multiple': sub(lambda r: r['qty'] == 'multiple')},
    'holdout_single_crop': metrics([r['label'] for r in hold if r['qty'] == 'single'], [pp for r, pp in zip(hold, hold_p) if r['qty'] == 'single'], thr),
    'same_images_as_tier0': same,
    'onnx': {'path': onnx_path, 'bytes': os.path.getsize(onnx_path)},
    'caveats': ['Labels are the dataset authors\' healthy/unhealthy folders, not procurement grades.',
                'One phone, one city; field photos will differ.',
                'Multiple-bulb photos inherit the image label, so a healthy bulb in an "unhealthy" photo counts as unhealthy.'],
}
json.dump(report, open('reports/zenodo_tier1.json', 'w'), indent=2)
print(json.dumps(report['holdout_image_level']['all']), 'same-images:', json.dumps(same))
