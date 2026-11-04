# ml/: dataset, training and evaluation (Phase 1)

This folder turns raw datasets into a trained detector, and produces the numbers we quote
(dataset stats, per-class mAP vs a COCO baseline). Every number comes from a script and
lands in `results/`; nothing is typed in by hand.

## The idea in 60 seconds

- **Detector**: [YOLO26](https://docs.ultralytics.com) "s" (small) from Ultralytics. It takes an
  image and returns boxes + class + confidence. We start from weights pretrained on COCO (a
  general dataset of everyday objects) and *fine-tune* them on Indian road images. That is
  called transfer learning: the network already knows what wheels, people and edges look
  like, so it only has to learn our 11 classes and Indian road scenes.
- **Why IDD**: COCO has no auto-rickshaws and few Indian street scenes. The India Driving
  Dataset (IDD) has tens of thousands of dashcam frames from Indian roads with boxes for cars, autos,
  two-wheelers, animals and so on.
- **Why Roboflow datasets too**: IDD has no pothole, barricade, speed-breaker or debris boxes.
  Small community datasets from Roboflow Universe fill that gap.
- **Why a COCO baseline**: to show the fine-tuning helped, we score the stock COCO model and
  our model on the *same* images with the *same* code.
- **mAP (mean average precision)**: the standard detection score, 0 to 1. For each class we
  sweep the confidence threshold and measure precision (how many detections were right) vs
  recall (how many objects were found); AP is the area under that curve. AP50 counts a box as
  right if it overlaps the true box by 50% (IoU >= 0.5); AP50-95 averages stricter overlaps
  too, so it also rewards tight boxes. Our implementation is tested to match the official
  COCO evaluator (pycocotools) exactly.

## Classes

Defined once in [`configs/classes.yaml`](../configs/classes.yaml) (shared with perception and
backend). Source label mappings: [`idd_mapping.yaml`](configs/idd_mapping.yaml),
[`obstacle_mapping.yaml`](configs/obstacle_mapping.yaml), and for the baseline
[`coco_map.yaml`](configs/coco_map.yaml).

| id | class | from |
|---:|---|---|
| 0 | car | IDD `car` |
| 1 | bus | IDD `bus` |
| 2 | truck | IDD `truck`, `caravan`, `trailer` |
| 3 | two_wheeler | IDD `motorcycle`, `bicycle` |
| 4 | auto_rickshaw | IDD `autorickshaw` |
| 5 | pedestrian | IDD `person` |
| 6 | animal | IDD `animal` |
| 7-10 | pothole, barricade, speed_breaker, debris | Roboflow datasets you choose |

Dropped IDD labels: `rider` (the two-wheeler box already covers it), `vehicle fallback`,
`traffic sign`, `traffic light`, `train`. If your download contains a label not in the
mapping, the converter stops and names it.

## Setup (Windows, PowerShell, from the repo root)

```powershell
# one-time: install uv (Python package manager) — https://docs.astral.sh/uv/
uv venv --python 3.11
.venv\Scripts\activate
uv pip install -e "ml[dev]"          # converters + tests (light, no PyTorch)
pytest ml                            # should print "30 passed"
```

You only need `ml[train]` (Ultralytics + PyTorch, a few GB) on the machine that trains or
evaluates. On Kaggle the notebook installs it for you.

## Step by step

All commands run from the repo root. Raw data goes in `data/raw/` (gitignored).

**1. Convert IDD** (after downloading and unzipping *IDD Detection* to `data/raw/IDD_Detection`):

```powershell
python -m dashcam_ml.convert.idd --root data/raw/IDD_Detection --out data/processed/idd
```

It prints every label it found with its count and target class. Check that list once. Images
are shrunk to 1280 px on the long side (`--max-side`, labels are unaffected because YOLO
labels are relative) so the dataset is smaller to upload. Try `--limit 50` first for a
quick dry run.

**2. Convert each obstacle dataset.** On Roboflow Universe, pick a dataset, click
*Download Dataset* → format **YOLOv8** → *download zip*, and unzip it into
`data/raw/<name>`. Add an entry for it in `ml/configs/obstacle_mapping.yaml` (source URL,
licence, and a target for every class name in its `data.yaml`), then:

```powershell
python -m dashcam_ml.convert.roboflow --src data/raw/<name> --dataset-name <name>
```

**3. Merge** into one dataset and write the stats:

```powershell
python -m dashcam_ml.merge --idd data/processed/idd --obstacles data/processed/obstacles
```

Output: `data/processed/merged/` (with `data.yaml`) and `results/dataset_stats.md` (images and
boxes per class, per split, per source, with licences). Commit the stats files.

**4. Train on Kaggle.** Zip `data/processed/merged` and upload it as a **private** Kaggle
dataset (*Datasets → New Dataset*), then open
[`notebooks/kaggle_train.ipynb`](notebooks/kaggle_train.ipynb) on Kaggle and follow its first
cell. It runs:

```
python -m dashcam_ml.train --config ml/configs/train/yolo26s_idd.yaml
```

The config explains each setting. Override anything with `--set train.epochs=40` etc.

**5. Evaluate** (end of the notebook, or anywhere with a GPU):

```
python -m dashcam_ml.evaluate --weights weights/best.pt --baseline yolo26s.pt --crosscheck
```

Writes `results/phase1_eval.md` + `.json`: per-class AP50 and AP50-95 for both models,
"shared-class" mAP (only classes COCO also has: the fair comparison) and "all-class" mAP,
for all val images and separately for IDD and obstacle images. `--limit N` writes to
`results/phase1_eval_smoke.*` instead, so a quick test can never overwrite a real result.

## What to expect (qualitative; no numbers until we run it)

- **auto_rickshaw** goes from 0 (COCO has no such class) to a real score: the clearest win.
- **car / bus / truck / two_wheeler / pedestrian** should improve over COCO on IDD images, but
  by less, since COCO already knows these.
- **pothole / speed_breaker / debris** are likely the weakest classes: small, low-contrast,
  and few training images. Debris may be too rare to report.

## Known limitations (also in the eval report)

- **Partial labels.** IDD images contain unlabelled potholes; pothole images contain
  unlabelled cars. The model is partly taught to treat those as background, which can lower
  recall. We measure first; if it hurts, the fix is pseudo-labelling (label road users on
  obstacle images with the IDD-only model, then retrain).
- **IDD val is not "the real world".** It comes from the same cities and cameras as IDD train.
  Your own footage (Phase 5) is the honest test.
- **Licences.** IDD is for research / non-commercial use; Roboflow datasets vary. See
  [`docs/datasets.md`](../docs/datasets.md). Trained weights are not committed.
