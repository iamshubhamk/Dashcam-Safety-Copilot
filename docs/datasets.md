# Datasets and licences

| dataset | used for | licence | where recorded |
|---|---|---|---|
| IDD Detection (IIIT Hyderabad / Intel) | road users (classes 0-6) | IDD terms of use: research and non-commercial use; requires registration at idd.insaan.iiit.ac.in | this file |
| Roboflow Universe obstacle datasets | pothole, barricade, speed_breaker, debris | per dataset (often CC BY 4.0, sometimes non-commercial) | `ml/configs/obstacle_mapping.yaml`, copied into `results/dataset_stats.md` by `dashcam_ml.merge` |
| COCO-pretrained YOLO26 weights (Ultralytics) | starting weights + baseline | AGPL-3.0 (Ultralytics) | this file |

Rules for this repo:

- Raw data, processed data and trained weights are never committed (`.gitignore`).
- Every obstacle dataset must have `source` and `license` filled in before it's merged; the
  merge report shows `UNKNOWN` otherwise.
- Because IDD is non-commercial, this project is a portfolio/research project. Using it in a
  real fleet product would need different training data or permission from IDD's owners.
- Ultralytics is AGPL-3.0. Fine for an open-source portfolio repo; a closed commercial
  product would need an Ultralytics enterprise licence.
