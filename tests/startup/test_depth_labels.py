"""Run in cvat_worker with PYTHONPATH=/app/shared."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
from depth_config import CameraCalibration, DepthConfig
from depth_estimation import align_depth
from utilities.depth_archive import extract_depth_archive
from utilities.depth_label_links import link_depth_to_coco


class DepthLabelsTests(unittest.TestCase):
    def test_coco_links_only_matching_camera_segment_and_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            detection_dir = root / "job_runs/front_regular/1/1/segments/0"
            depth_dir = root / "job_runs/front_regular/2/1/segments/0"
            detection_dir.mkdir(parents=True)
            depth_dir.mkdir(parents=True)
            coco = {"images": [{"id": 1, "file_name": "00012.png"}, {"id": 2, "file_name": "00013.png"}],
                    "annotations": [{"image_id": 1, "bbox": [1, 2, 3, 4]}]}
            (detection_dir / "data.json").write_text(json.dumps(coco))
            index = {"kind": "monocular_depth", "camera": "front_regular", "segment_id": 0,
                     "images": [{"frame_id": 12, "depth_file": "depth/00012.npz", "units": "meters", "intrinsics": None}]}
            (depth_dir / "data.json").write_text(json.dumps(index))
            link_depth_to_coco(root)
            linked = json.loads((detection_dir / "data.json").read_text())
            self.assertEqual(linked["annotations"], coco["annotations"])
            self.assertEqual(linked["images"][0]["depth_labels"][0]["file"], "job_runs/front_regular/2/1/segments/0/depth/00012.npz")
            self.assertNotIn("depth_labels", linked["images"][1])

    def test_metric_scaling_uses_processed_focal_length(self):
        calibration = CameraCalibration(width=100, height=80, fx=600, fy=800)
        depth, units, matrix = align_depth(np.full((40, 50), 2), (100, 80), calibration)
        self.assertEqual(depth.shape, (80, 100))
        self.assertEqual(depth.dtype, np.float32)
        self.assertTrue(np.allclose(depth, 2 * 350 / 300))
        self.assertEqual(units, "meters")
        self.assertEqual(matrix[0][0], 600)

    def test_uncalibrated_output_is_never_meters(self):
        _, units, matrix = align_depth(np.ones((14, 28)), (280, 140))
        self.assertEqual(units, "focal_normalized")
        self.assertIsNone(matrix)
        with self.assertRaises(ValueError):
            DepthConfig(require_metric=True).calibration_for("front_wide")

    def test_wrong_resolution_and_invalid_prediction_rejected(self):
        calibration = CameraCalibration(width=200, height=80, fx=600, fy=600)
        with self.assertRaises(ValueError):
            align_depth(np.ones((14, 28)), (100, 80), calibration)
        with self.assertRaises(ValueError):
            align_depth(np.array([[float("nan")]]), (10, 10))

    def test_archive_roundtrip_and_missing_map_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive_path = root / "labels.zip"
            index = {"kind": "monocular_depth", "schema_version": 1,
                     "images": [{"depth_file": "depth/00001.npz"}]}
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data.json", json.dumps(index))
                archive.writestr("depth/00001.npz", b"test")
            extract_depth_archive(archive_path, root / "export")
            self.assertEqual((root / "export/depth/00001.npz").read_bytes(), b"test")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data.json", json.dumps(index))
            with self.assertRaises(ValueError):
                extract_depth_archive(archive_path, root / "invalid")

    def test_archive_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive_path = root / "labels.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data.json", "{}")
                archive.writestr("../escape.npz", b"test")
            with self.assertRaises(ValueError):
                extract_depth_archive(archive_path, root / "export")


if __name__ == "__main__":
    unittest.main()
