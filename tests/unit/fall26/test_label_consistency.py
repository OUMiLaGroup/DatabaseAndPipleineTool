"""
test_label_consistency.py

Simple demonstration unit test for the OpenPilot Data Pipeline capstone.

Goal:
    When the CVAT/object-detection stage labels an object in a video frame
    (e.g. "pedestrian", "car", "cyclist"), that label should be roughly
    consistent with the object's physical dimensions. If a "pedestrian"
    bounding box is 4 meters wide, something is probably wrong -- either
    the class label is wrong, or the dimensions/bounding box are wrong.

    This script hardcodes a few sample Detection objects (as would come
    from a detection model / CVAT export) and checks each one's dimensions
    against a simple table of "reasonable" size ranges per object class.
    Any detection outside the expected range is flagged as a possible
    mislabel.

    This is intentionally simple: no ML, no real data, just a
    demonstration of the kind of sanity-check test the team could grow
    into a real validation step in the pipeline.
"""

from dataclasses import dataclass
import unittest


# ---------------------------------------------------------------------------
# A minimal stand-in for a real detection record coming out of CVAT / a model
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    object_type: str      # e.g. "pedestrian", "car", "cyclist", "truck"
    width_m: float         # bounding box width in meters
    height_m: float        # bounding box height in meters
    length_m: float        # bounding box length in meters
    confidence: float      # model confidence score, 0.0 - 1.0


# ---------------------------------------------------------------------------
# Expected "reasonable" dimension ranges per object class (min, max) in meters
# These are rough, illustrative numbers -- not real-world engineering specs.
# ---------------------------------------------------------------------------
EXPECTED_DIMENSIONS = {
    "pedestrian": {"width": (0.3, 1.0), "height": (1.2, 2.2), "length": (0.3, 1.0)},
    "cyclist":    {"width": (0.4, 1.0), "height": (1.2, 2.2), "length": (1.5, 2.2)},
    "car":        {"width": (1.5, 2.2), "height": (1.3, 1.9), "length": (3.5, 5.5)},
    "truck":      {"width": (2.0, 3.0), "height": (2.5, 4.5), "length": (6.0, 16.0)},
}

MIN_CONFIDENCE = 0.5


def flag_detection_issues(detection: Detection) -> list[str]:
    """
    Compare a Detection's dimensions/confidence against the expected
    ranges for its labeled object_type.

    Returns a list of human-readable issue strings. An empty list means
    the detection looks consistent.
    """
    issues = []

    expected = EXPECTED_DIMENSIONS.get(detection.object_type)
    if expected is None:
        issues.append(f"Unknown object_type '{detection.object_type}' - no size rules defined")
        return issues

    for dim_name, (low, high) in expected.items():
        value = getattr(detection, f"{dim_name}_m")
        if not (low <= value <= high):
            issues.append(
                f"{dim_name} of {value}m is outside expected range "
                f"[{low}, {high}]m for object_type '{detection.object_type}'"
            )

    if detection.confidence < MIN_CONFIDENCE:
        issues.append(
            f"confidence {detection.confidence} is below minimum threshold {MIN_CONFIDENCE}"
        )

    return issues


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
class TestLabelConsistency(unittest.TestCase):

    def test_normal_pedestrian_has_no_issues(self):
        detection = Detection("pedestrian", width_m=0.5, height_m=1.7, length_m=0.5, confidence=0.91)
        self.assertEqual(flag_detection_issues(detection), [])

    def test_oversized_pedestrian_is_flagged(self):
        # Same "pedestrian" label, but dimensions look more like a car.
        detection = Detection("pedestrian", width_m=1.9, height_m=1.6, length_m=4.5, confidence=0.88)
        issues = flag_detection_issues(detection)
        self.assertTrue(len(issues) > 0, "Oversized pedestrian should raise at least one issue")

    def test_normal_car_has_no_issues(self):
        detection = Detection("car", width_m=1.8, height_m=1.5, length_m=4.6, confidence=0.95)
        self.assertEqual(flag_detection_issues(detection), [])

    def test_undersized_car_is_flagged(self):
        # Label says "car" but the box is pedestrian-sized.
        detection = Detection("car", width_m=0.5, height_m=1.7, length_m=0.6, confidence=0.80)
        issues = flag_detection_issues(detection)
        self.assertTrue(len(issues) > 0, "Undersized car should raise at least one issue")

    def test_low_confidence_is_flagged(self):
        detection = Detection("cyclist", width_m=0.6, height_m=1.7, length_m=1.8, confidence=0.20)
        issues = flag_detection_issues(detection)
        self.assertTrue(any("confidence" in issue for issue in issues))

    def test_unknown_object_type_is_flagged(self):
        detection = Detection("traffic_cone", width_m=0.3, height_m=0.7, length_m=0.3, confidence=0.9)
        issues = flag_detection_issues(detection)
        self.assertTrue(any("Unknown object_type" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
