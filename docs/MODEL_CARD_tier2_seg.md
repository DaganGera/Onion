# Model card: Tier 2 onion instance segmentation

**Job:** find every onion in a photo and draw its outline, so each bulb can be sized and checked for defects. It replaces the colour-rule detector (Tier 0) for this step; Tier 0 still measures defects inside each outline and is the fallback when the model can't load.

**Architecture:** U-Net with a MobileNetV3-Large encoder (timm, Apache-2.0, ImageNet start) and a light decoder. It outputs three classes per pixel: background, onion interior and onion edge. On the phone, interior blobs become seeds, and every onion pixel joins its nearest seed through onion pixels. The edge band between touching onions is never a seed, so touching onions stay separate. Input: long side 512 px. Size: 16 MB, full precision (8-bit versions lost too much counting accuracy; see docs/DECISIONS.md 18). Runs in the app's worker with ONNX Runtime Web (MIT).

**Training data:** real photos from Zenodo 10.5281/zenodo.20254934 (CC-BY 4.0), 828 photos from the training blocks. Labels were made offline by OWLv2 (text prompt "onion", Apache-2.0) and SAM ViT-B (Apache-2.0); neither ships in the app. Training-only augmentation pasted real onion cut-outs onto real backgrounds, sometimes over the printed calibration mat artwork, so the model learns that paper, markers and printing are not onions. Scripts: `scripts/teacher_masks.py`, `scripts/train_seg.py`.

**Evaluation:** on held-out photos (never seen in training) whose onions were counted by eye, see docs/EVALUATION.md, "Finding and counting onions" (generated from `reports/count_eval.json`). On the team's first field photo (printed mat on a wooden table, 5 onions plus one small onion on a marker), it outlined exactly those 6 and ignored the mat, table, cable and bag.

**Known limits:** trained on one public dataset (one phone, markets in one city). Deep piles where onions hide under others are still ambiguous, even for a person. The count-by-eye truth set is small (18 clear photos). Field photos from the team's phones should be added (docs/HUMAN_TASKS.md T3) and the model retrained.
