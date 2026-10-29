"""Link selected pixel maps into COCO image labels without changing box labels."""
import json
from pathlib import Path


def link_depth_to_coco(export_root: Path):
    indices = []
    coco_files = []
    for path in (export_root / "job_runs").rglob("data.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") == "monocular_depth":
            for image in data["images"]:
                indices.append((data["camera"], data["segment_id"], image,
                                (path.parent / image["depth_file"]).relative_to(export_root).as_posix()))
        elif "images" in data and "annotations" in data:
            coco_files.append((path, data))
    for path, coco in coco_files:
        relative = path.relative_to(export_root).parts
        camera, segment_id = relative[1], int(relative[-2])
        for image in coco["images"]:
            stem = Path(image["file_name"]).stem
            if not stem.isdigit():
                continue
            links = [{"file": depth_file, "units": depth["units"], "depth_convention": "camera_z",
                      "intrinsics": depth["intrinsics"]}
                     for depth_camera, depth_segment, depth, depth_file in indices
                     if depth_camera == camera and depth_segment == segment_id and depth["frame_id"] == int(stem)]
            if links:
                image["depth_labels"] = links
        path.write_text(json.dumps(coco), encoding="utf-8")
