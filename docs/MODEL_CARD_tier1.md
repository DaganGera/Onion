# Model card: Tier 1 learned cross-check

**Architecture:** MobileNetV3-Small from torchvision (BSD-3-Clause code; ImageNet-initialised weights), final layer replaced by a two-class head (healthy, unhealthy). Input: a 128 px square crop around one bulb, cut by the Tier-0 segmentation. Exported to ONNX (`apps/web/public/models/tier1.onnx`) and run on the phone with ONNX Runtime Web (MIT) in the vision worker.

**Training data:** single-bulb photos from the public Zenodo dataset 10.5281/zenodo.20254934 (CC-BY 4.0), where the folder label (healthy or unhealthy) is exactly the bulb's label. Images are grouped in blocks of 25 consecutive ids; blocks 1 to 3 of every 5 train the model, block 0 chooses the epoch and threshold, block 4 is the reported holdout. Multi-bulb photos are never used for training because their label applies to the whole photo. No synthetic or pasted images. Training script: `scripts/train_tier1.py` (PyTorch 2.11, CUDA).

**How the app uses it:** Tier 1 never changes a measurement. When it is confident a bulb is unhealthy while Tier 0 measured neither rot nor blackening on it, the bulb's confidence drops and the rule pack sends it to a person ("needs human check"). The bulb sheet shows the Tier-1 probability. The Tier-1 weights hash is part of the model hash printed on every receipt.

**Ship decision:** the brief says a learned model ships only where it beats Tier 0 on the holdout. The comparison on the same held-out photos is in docs/EVALUATION.md, and `apps/web/public/models/tier1.json` records `ship: true` or `false` accordingly. The app ignores the model when `ship` is false.

**Evaluation and caveats:** see docs/EVALUATION.md (generated from `reports/zenodo_tier1.json`). The labels are the dataset authors' healthy/unhealthy folders, not procurement grades; one phone and one city; a binary label cannot say which defect or how much, which is why the rule pack still uses Tier-0 area fractions for every verdict.

**Retraining:** `bash scripts/retrain.sh <corrections.json> <evidence dir> <crops dir>` adds every bulb an officer corrected in the app (exported from Settings) as a labelled crop, retrains, and regenerates the evaluation.
