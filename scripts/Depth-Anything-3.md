# Pixel depth labels with Depth Anything 3

MiLa now supports a `depth` job using the pinned upstream DA3METRIC-LARGE model.
It processes each image independently, stores float32 numerical depth maps in
MinIO, and exports them alongside images and detection labels. No database
migration is needed. Model weights download automatically on first use and are
kept in the `mila_model_cache` Docker volume.

## Using the dashboard

1. Open an uploaded route, create a job, select **Monocular Depth (DA3)**, and
   select the camera to process. The default definition is installed by the launcher.
2. Wait for the job to succeed. This processes every image in every segment;
   CPU processing is slower than GPU processing.
3. Use **Export** on the depth job for images, logs, depth maps and their index.
4. If a General Detection job has also succeeded for the same route and camera,
   its row offers **Export + depth**. This selects the most recently completed
   depth job for that camera and includes both sets of labels in one ZIP.
   COCO `images` entries gain `depth_labels` references; bounding-box annotations
   remain intact. References are relative to the route folder in the ZIP.

Dense depth maps are numerical training labels, not CVAT bounding-box annotations.
They are exported through MiLa; the CVAT import action is disabled for depth jobs.

## Distances in meters require camera calibration

Without calibration, the job intentionally records `units: focal_normalized`.
These numbers are NOT meters. To generate estimated metric depth, create a new
job definition on the Job Definitions page, choose **Pixel Depth**, and give it
a distinct name such as `Calibrated Front Depth`.

In its Config editor, set `calibrations` to a JSON object containing the camera
name and **width, height, fx, fy**. Width and height must match the original
extracted PNG. The focal lengths fx/fy must be in pixels at that same resolution.
Optional `cx`/`cy` specify the principal point; omission uses the image center.
For example, the following is the shape of the configuration (replace the
placeholders with actual calibration values; do not paste it literally):

```text
{"front_regular":{"width":IMAGE_WIDTH,"height":IMAGE_HEIGHT,"fx":CALIBRATED_FX,"fy":CALIBRATED_FY,"cx":CALIBRATED_CX,"cy":CALIBRATED_CY}}
```

Set `require_metric` to `true` to reject jobs without calibration for the chosen
camera. A calibration with mismatched image dimensions fails rather than silently
generating incorrectly scaled distances. Do not reuse one camera's calibration
for a different lens or recording device. Use a separate definition per device
and camera if recordings have different hardware.

For OpenPilot footage, the original device type and camera sensor identify the
appropriate `DEVICE_CAMERAS` entry in OpenPilot's camera configuration. MiLa's
current saved logs do not preserve these identifiers or intrinsics. Obtain them
from the recording's original rlog/device metadata or the data provider. The
`liveCalibration` pitch/yaw/roll values describe orientation and do not replace
focal-length calibration. Do not guess focal length from image dimensions.

Upstream's [metric conversion convention](https://github.com/ByteDance-Seed/Depth-Anything-3#faq)
is `Z = mean(fx, fy) * network_depth / 300`. MiLa scales fx/fy to the
model's processed resolution before applying this formula, then resizes the map
back to the original PNG resolution without cropping. This restores alignment,
but does not create additional measured detail beyond the inference resolution.
The default `process_res` is 504; 280 can reduce CPU cost at reduced detail.

## Export format

```text
route_.../
  segments/0/images/front_regular/123.png
  job_runs/front_regular/<depth-definition>/<run>/segments/0/
    data.json
    depth/00123.npz
```

Each `data.json` image entry records the original frame ID, image filename,
export image path, map path, original and processed dimensions, units and camera
intrinsics. Route, camera, segment and pinned model/source revisions are recorded
in the index. Frame IDs, rather than COCO image IDs, join detection and depth jobs.

The NPZ contains `depth` (float32, H × W) and `valid` (boolean, H × W). The valid
mask excludes invalid numbers and predicted sky. It is not a calibrated confidence
score. Depth is estimated camera-axis Z distance, not Euclidean distance to the
camera or distance to the front of the vehicle.

```python
import numpy as np
with np.load("depth/00123.npz", allow_pickle=False) as labels:
    depth = labels["depth"]
    valid = labels["valid"]
    # Check data.json units before treating a value as meters.
    if valid[y, x]:
        print(float(depth[y, x]))
```

Later, object-distance code can aggregate valid pixels inside an object mask or
box. Boxes include background pixels; object masks generally provide a better
estimate. Validate against known distances before relying on metric accuracy.

## NVIDIA GPU option

The default installation runs on CPU. For a compatible NVIDIA GPU and driver
with GPU access working in Docker Desktop/WSL2, start the inference worker using:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.gpu.yml up -d --build cvat_worker
docker compose exec -T cvat_worker python -c "import torch; print(torch.cuda.is_available())"
```

`device: auto` chooses CUDA when available. `device: cuda` fails clearly if it is
not available; `device: cpu` forces CPU. CUDA inference uses mixed precision and
one frame per pass. Use the GPU override whenever recreating the worker; the
launcher's regular Compose invocation does not enable this optional override.
GPU behavior has not been validated on this computer, which currently reports
CUDA unavailable. RTX 4080/5080 operation requires a matching PyTorch/CUDA build
and host driver; the override alone does not install or validate drivers.

## Developer verification

Tests in `tests/startup/test_depth_labels.py` cover metric scaling after resizing,
uncalibrated units, resolution mismatch, invalid values, safe archive extraction,
and matching COCO image references. Run them in the cvat_worker container.
`tests/startup/smoke_depth_inference.py` performs real CPU inference on one frame
from the currently uploaded sample route without queuing a complete route.
`tests/startup/smoke_depth_pipeline.py` additionally exercises the production
segment worker, MinIO storage and dataset export extraction on that frame using
fake database services. Its temporary MinIO object is removed after verification.

The implementation uses upstream's core model and image preprocessor. Its
requirements intentionally exclude optional reconstruction, Gaussian splatting,
COLMAP and web UI dependencies. Importing upstream's full `api`/CLI requires those
extra dependencies; the MiLa adapter does not use them.

Model: [DA3METRIC-LARGE](https://huggingface.co/depth-anything/DA3METRIC-LARGE)
(Apache 2.0 per its model card). Code:
[official Depth Anything 3 repository](https://github.com/ByteDance-Seed/Depth-Anything-3).
