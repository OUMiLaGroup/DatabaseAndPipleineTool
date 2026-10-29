"""Monocular DA3 inference and original-image-aligned depth label archives.

Uses DA3's core model and preprocessor directly to avoid installing its unrelated
3D reconstruction/export applications. Models and weights are pinned together.
"""
import json
import logging
import zipfile
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from depth_config import DepthConfig

logger = logging.getLogger(__name__)
SOURCE_REVISION = "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"


@lru_cache(maxsize=1)
def _load_model(model_name: str, revision: str, requested_device: str):
    import torch
    from huggingface_hub import hf_hub_download
    from safetensors.torch import load_model
    from depth_anything_3.cfg import create_object, load_config
    from depth_anything_3.registry import MODEL_REGISTRY
    from depth_anything_3.utils.io.input_processor import InputProcessor

    device = "cuda" if requested_device == "auto" and torch.cuda.is_available() else requested_device
    if device == "auto":
        device = "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but is unavailable. Enable the GPU Compose override with a supported NVIDIA driver, or select cpu/auto.")
    logger.info("Loading %s on %s; first use downloads model weights", model_name, device)
    # HF weights include the `model.` prefix used by the upstream API wrapper.
    holder = torch.nn.Module()
    holder.model = create_object(load_config(MODEL_REGISTRY["da3metric-large"]))
    weights = hf_hub_download(model_name, "model.safetensors", revision=revision)
    load_model(holder, weights, strict=True)
    holder.eval().to(device)
    return holder.model, InputProcessor(), device


def align_depth(raw_depth, original_size, calibration=None):
    """Return float32 Z-depth; scale focal length to the model's resized image."""
    width, height = original_size
    raw = np.asarray(raw_depth, dtype=np.float32)
    if raw.ndim != 2 or not np.all(np.isfinite(raw)) or np.any(raw <= 0):
        raise ValueError("Model returned invalid depth values; no depth labels were saved.")
    processed_h, processed_w = raw.shape
    units = "focal_normalized"
    intrinsics = None
    if calibration is not None:
        if (calibration.width, calibration.height) != (width, height):
            raise ValueError("Calibration resolution must match the original image. Supply calibration for this camera's extracted image resolution.")
        # Upstream metric model convention: Z = mean(fx, fy) * network_depth / 300.
        # Its no-crop resize changes horizontal and vertical focal lengths separately.
        focal = (calibration.fx * processed_w / width + calibration.fy * processed_h / height) / 2
        raw = raw * (focal / 300.0)
        units = "meters"
        intrinsics = [[calibration.fx, 0, calibration.cx if calibration.cx is not None else width / 2],
                      [0, calibration.fy, calibration.cy if calibration.cy is not None else height / 2], [0, 0, 1]]
    depth = np.asarray(Image.fromarray(raw).resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32).copy()
    return depth, units, intrinsics


def create_depth_archive(image_dir: Path, output_path: Path, config: DepthConfig, *, camera: str, route_id: str, segment_id: int):
    import torch
    calibration = config.calibration_for(camera)
    images = sorted(image_dir.glob("*.png"))
    if not images:
        raise ValueError(f"No images are available for depth estimation on {camera}.")
    model, processor, device = _load_model(config.model_name, config.model_revision, config.device)
    maps_dir = image_dir / "depth"
    maps_dir.mkdir(exist_ok=True)
    index = {"schema_version": 1, "kind": "monocular_depth", "model": config.model_name,
             "model_revision": config.model_revision, "source_revision": SOURCE_REVISION,
             "route_id": route_id, "segment_id": segment_id, "camera": camera,
             "depth_convention": "camera_z", "process_res": config.process_res,
             "resize_method": "upper_bound_resize", "images": []}
    for number, path in enumerate(images, 1):
        with Image.open(path) as source:
            image = source.convert("RGB")
        # One image per forward pass: monocular operation and bounded activation memory.
        tensors, _, _ = processor([image], process_res=config.process_res,
                                  process_res_method="upper_bound_resize", num_workers=1)
        batch = tensors[None].to(device).float()
        precision = torch.autocast("cuda", dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if device == "cuda" else nullcontext()
        with torch.inference_mode(), precision:
            output = model(batch)
        raw = output["depth"].float().cpu().numpy().reshape(tuple(tensors.shape[-2:]))
        depth, units, intrinsics = align_depth(raw, image.size, calibration)
        valid = np.isfinite(depth) & (depth > 0)
        if "sky" in output:
            non_sky = output["sky"].float().cpu().numpy().reshape(raw.shape) < 0.3
            valid &= np.asarray(Image.fromarray(non_sky.astype(np.uint8)).resize(image.size, Image.Resampling.NEAREST), dtype=bool)
        map_path = maps_dir / f"{path.stem}.npz"
        np.savez_compressed(map_path, depth=depth, valid=valid)
        index["images"].append({"frame_id": int(path.stem), "file_name": path.name,
            "export_image": f"segments/{segment_id}/images/{camera}/{int(path.stem)}.png",
            "depth_file": f"depth/{map_path.name}", "width": image.width, "height": image.height,
            "processed_width": raw.shape[1], "processed_height": raw.shape[0],
            "units": units, "intrinsics": intrinsics})
        logger.info("Depth frame %s/%s: %s (%s)", number, len(images), path.name, units)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("data.json", json.dumps(index, indent=2))
        for path in maps_dir.glob("*.npz"):
            archive.write(path, f"depth/{path.name}")
    return output_path
