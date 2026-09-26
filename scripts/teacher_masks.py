"""Teacher labels for the Tier-2 onion segmentation student (offline only, never shipped).

OWLv2 (google/owlv2-base-patch16-ensemble, Apache-2.0) finds onions from a text
prompt; SAM (facebook/sam-vit-base, Apache-2.0) turns each box into a mask.
Output per image: <out>/<name>.png, a uint8 instance map (0 = background,
1..254 = onion instances) at the image's own size, plus <out>/index.csv.

Usage:
  python scripts/teacher_masks.py --list files.txt --out D:/onion/teacher [--viz 20]
"""
import argparse, csv, os
import numpy as np
import torch
from PIL import Image
from transformers import Owlv2ForObjectDetection, Owlv2Processor, SamModel, SamProcessor
from torchvision.ops import nms

p = argparse.ArgumentParser()
p.add_argument('--list', required=True)
p.add_argument('--out', required=True)
p.add_argument('--thr', type=float, default=0.18)
p.add_argument('--viz', type=int, default=0)
p.add_argument('--maxside', type=int, default=1024)
a = p.parse_args()
os.makedirs(a.out, exist_ok=True)
dev = 'cuda'
owl_p = Owlv2Processor.from_pretrained('google/owlv2-base-patch16-ensemble')
owl = Owlv2ForObjectDetection.from_pretrained('google/owlv2-base-patch16-ensemble').to(dev).eval().half()
sam_p = SamProcessor.from_pretrained('facebook/sam-vit-base')
sam = SamModel.from_pretrained('facebook/sam-vit-base').to(dev).eval()
QUERIES = [['a photo of an onion', 'a red onion', 'a white onion', 'an onion bulb']]

files = [l.strip() for l in open(a.list, encoding='utf8') if l.strip()]
idx = open(os.path.join(a.out, 'index.csv'), 'a', newline='')
wr = csv.writer(idx)
for k, f in enumerate(files):
    name = os.path.splitext(os.path.basename(f))[0]
    dst = os.path.join(a.out, name + '.png')
    if os.path.exists(dst):
        continue
    img = Image.open(f).convert('RGB')
    s = min(1.0, a.maxside / max(img.size))
    if s < 1: img = img.resize((round(img.width * s), round(img.height * s)), Image.BILINEAR)
    W, H = img.size
    with torch.no_grad():
        inp = owl_p(text=QUERIES, images=img, return_tensors='pt').to(dev)
        inp['pixel_values'] = inp['pixel_values'].half()
        out = owl(**inp)
        # OWLv2 pads to a square: boxes are relative to max(W, H).
        side = max(W, H)
        res = owl_p.post_process_grounded_object_detection(out, threshold=a.thr, target_sizes=[(side, side)])[0]
        boxes, scores = res['boxes'].float(), res['scores'].float()
        if len(boxes):
            keep = nms(boxes, scores, 0.4)
            boxes, scores = boxes[keep], scores[keep]
            boxes[:, 0::2] = boxes[:, 0::2].clamp(0, W - 1); boxes[:, 1::2] = boxes[:, 1::2].clamp(0, H - 1)
            # Drop boxes that are most of the image (the whole pile / the table).
            area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
            ok = area < 0.5 * W * H
            boxes, scores = boxes[ok], scores[ok]
        inst = np.zeros((H, W), np.uint8)
        n = 0
        if len(boxes):
            order = torch.argsort(scores)  # paint high scores last so they win overlaps
            bl = boxes[order].tolist()
            sp = sam_p(img, input_boxes=[bl], return_tensors='pt').to(dev)
            so = sam(**sp, multimask_output=False)
            masks = sam_p.image_processor.post_process_masks(so.pred_masks.cpu(), sp['original_sizes'].cpu(), sp['reshaped_input_sizes'].cpu())[0][:, 0].numpy()
            iou = so.iou_scores.cpu().numpy()[0, :, 0]
            for j, m in enumerate(masks):
                x0, y0, x1, y1 = [int(v) for v in bl[j]]
                box_area = max(1, (x1 - x0) * (y1 - y0))
                fill = m.sum() / box_area
                if iou[j] < 0.8 or fill < 0.45 or fill > 1.05 or m.sum() < 150:
                    continue
                n += 1
                inst[m] = min(254, n)
    Image.fromarray(inst).save(dst)
    wr.writerow([name, f, W, H, n]); idx.flush()
    if k < a.viz:
        v = np.array(img).copy()
        rng = np.random.default_rng(1)
        for i in range(1, n + 1):
            c = rng.integers(60, 255, 3)
            v[inst == i] = (0.45 * v[inst == i] + 0.55 * c).astype(np.uint8)
        Image.fromarray(v).save(os.path.join(a.out, 'viz_' + name + '.jpg'), quality=80)
    if k % 50 == 0: print(k, name, n, flush=True)
idx.close()
