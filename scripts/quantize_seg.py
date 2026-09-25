"""INT8 static quantisation (QDQ) of the Tier-2 segmentation model for the phone.

Calibrates on real tune-split photos. Keeps the float model if the INT8 model
disagrees on onion counts (checked by tools/eval_count.ts afterwards).
Usage: python scripts/quantize_seg.py --teacher D:/onion/teacher --models apps/web/public/models
"""
import argparse, csv, json, os, hashlib
import numpy as np
from PIL import Image
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from onnxruntime.quantization.shape_inference import quant_pre_process

p = argparse.ArgumentParser()
p.add_argument('--teacher', required=True)
p.add_argument('--models', default='apps/web/public/models')
p.add_argument('--n', type=int, default=60)
a = p.parse_args()
meta = json.load(open(os.path.join(a.models, 'seg.json')))
MEAN, STD = np.array(meta['mean'], np.float32), np.array(meta['std'], np.float32)
rows = list(csv.reader(open(os.path.join(a.teacher, 'index.csv'))))
blk = lambda n: (int(''.join(c for c in n if c.isdigit())) // 25) % 5
tune = [r for r in rows if blk(r[0]) == 0][: a.n]

class Reader(CalibrationDataReader):
    def __init__(self):
        self.it = iter(tune)
    def get_next(self):
        r = next(self.it, None)
        if r is None: return None
        img = Image.open(r[1]).convert('RGB').resize((512, 384), Image.BILINEAR)
        x = ((np.asarray(img, np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
        return {'x': x}

src = os.path.join(a.models, 'seg.onnx')
pre = os.path.join(a.models, 'seg.pre.onnx')
dst = os.path.join(a.models, 'seg.int8.onnx')
quant_pre_process(src, pre)
quantize_static(pre, dst, Reader(), quant_format=QuantFormat.QDQ, activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8, per_channel=True)
os.remove(pre)
print('float', os.path.getsize(src), 'int8', os.path.getsize(dst))
