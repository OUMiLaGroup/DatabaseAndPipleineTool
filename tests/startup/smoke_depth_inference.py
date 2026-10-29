"""Real one-frame inference without queueing an entire route or changing its labels."""
import json
import tempfile
from pathlib import Path
import numpy as np
from depth_config import DepthConfig
from depth_estimation import create_depth_archive
from services.minio_service import MinioService
from utilities.depth_archive import extract_depth_archive

storage = MinioService()
prefix = "v1/routes/db478799b6f9f210|0000000e--9ecd39f6bc/segment/0/front_regular/frames/"
image_object = next(storage.minio_client.list_objects(storage.bucket_name, prefix=prefix))
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    image_dir = root / "images"
    image_dir.mkdir()
    name = Path(image_object.object_name).name
    storage.minio_client.fget_object(storage.bucket_name, image_object.object_name, str(image_dir / name))
    archive = create_depth_archive(image_dir, root / "labels.zip", DepthConfig(device="cpu", process_res=280),
                                   camera="front_regular", route_id="validation", segment_id=0)
    index = extract_depth_archive(archive, root / "export")
    with np.load(root / "export" / index["images"][0]["depth_file"], allow_pickle=False) as labels:
        depth = labels["depth"]
        assert depth.shape == (index["images"][0]["height"], index["images"][0]["width"])
        assert np.all(np.isfinite(depth)) and np.all(depth > 0)
        print(json.dumps({"model": index["model"], "shape": list(depth.shape), "units": index["images"][0]["units"],
                          "min": float(depth.min()), "max": float(depth.max()), "valid_pixels": int(labels["valid"].sum())}))
