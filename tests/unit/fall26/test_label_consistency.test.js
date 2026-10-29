/**
 * test_label_consistency.test.js
 *
 * JavaScript port of the label consistency demonstration test.
 * Uses Node's built-in test runner (node:test) and assert module,
 * so there are no extra dependencies to install.
 *
 * Run with:
 *   node --test test_label_consistency.test.js
 *
 * (Requires Node.js 18+; this was written/verified against Node 22.)
 */

const test = require("node:test");
const assert = require("node:assert/strict");

// ---------------------------------------------------------------------------
// A minimal stand-in for a real detection record coming out of CVAT / a model
// ---------------------------------------------------------------------------
function makeDetection({ objectType, widthM, heightM, lengthM, confidence }) {
  return {
    objectType,   // e.g. "pedestrian", "car", "cyclist", "truck"
    widthM,       // bounding box width in meters
    heightM,      // bounding box height in meters
    lengthM,      // bounding box length in meters
    confidence,   // model confidence score, 0.0 - 1.0
  };
}

// ---------------------------------------------------------------------------
// Expected "reasonable" dimension ranges per object class (min, max) in meters
// These are rough, illustrative numbers -- not real-world engineering specs.
// ---------------------------------------------------------------------------
const EXPECTED_DIMENSIONS = {
  pedestrian: { width: [0.3, 1.0], height: [1.2, 2.2], length: [0.3, 1.0] },
  cyclist:    { width: [0.4, 1.0], height: [1.2, 2.2], length: [1.5, 2.2] },
  car:        { width: [1.5, 2.2], height: [1.3, 1.9], length: [3.5, 5.5] },
  truck:      { width: [2.0, 3.0], height: [2.5, 4.5], length: [6.0, 16.0] },
};

const MIN_CONFIDENCE = 0.5;

const DIM_TO_FIELD = {
  width: "widthM",
  height: "heightM",
  length: "lengthM",
};

/**
 * Compare a detection's dimensions/confidence against the expected
 * ranges for its labeled objectType.
 *
 * Returns an array of human-readable issue strings. An empty array
 * means the detection looks consistent.
 */
function flagDetectionIssues(detection) {
  const issues = [];

  const expected = EXPECTED_DIMENSIONS[detection.objectType];
  if (!expected) {
    issues.push(`Unknown objectType '${detection.objectType}' - no size rules defined`);
    return issues;
  }

  for (const [dimName, [low, high]] of Object.entries(expected)) {
    const value = detection[DIM_TO_FIELD[dimName]];
    if (value < low || value > high) {
      issues.push(
        `${dimName} of ${value}m is outside expected range [${low}, ${high}]m ` +
        `for objectType '${detection.objectType}'`
      );
    }
  }

  if (detection.confidence < MIN_CONFIDENCE) {
    issues.push(`confidence ${detection.confidence} is below minimum threshold ${MIN_CONFIDENCE}`);
  }

  return issues;
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------
test("normal pedestrian has no issues", () => {
  const detection = makeDetection({ objectType: "pedestrian", widthM: 0.5, heightM: 1.7, lengthM: 0.5, confidence: 0.91 });
  assert.deepEqual(flagDetectionIssues(detection), []);
});

test("oversized pedestrian is flagged", () => {
  // Same "pedestrian" label, but dimensions look more like a car.
  const detection = makeDetection({ objectType: "pedestrian", widthM: 1.9, heightM: 1.6, lengthM: 4.5, confidence: 0.88 });
  const issues = flagDetectionIssues(detection);
  assert.ok(issues.length > 0, "Oversized pedestrian should raise at least one issue");
});

test("normal car has no issues", () => {
  const detection = makeDetection({ objectType: "car", widthM: 1.8, heightM: 1.5, lengthM: 4.6, confidence: 0.95 });
  assert.deepEqual(flagDetectionIssues(detection), []);
});

test("undersized car is flagged", () => {
  // Label says "car" but the box is pedestrian-sized.
  const detection = makeDetection({ objectType: "car", widthM: 0.5, heightM: 1.7, lengthM: 0.6, confidence: 0.80 });
  const issues = flagDetectionIssues(detection);
  assert.ok(issues.length > 0, "Undersized car should raise at least one issue");
});

test("low confidence is flagged", () => {
  const detection = makeDetection({ objectType: "cyclist", widthM: 0.6, heightM: 1.7, lengthM: 1.8, confidence: 0.20 });
  const issues = flagDetectionIssues(detection);
  assert.ok(issues.some((issue) => issue.includes("confidence")));
});

test("unknown object type is flagged", () => {
  const detection = makeDetection({ objectType: "traffic_cone", widthM: 0.3, heightM: 0.7, lengthM: 0.3, confidence: 0.9 });
  const issues = flagDetectionIssues(detection);
  assert.ok(issues.some((issue) => issue.includes("Unknown objectType")));
});

module.exports = { flagDetectionIssues, makeDetection, EXPECTED_DIMENSIONS };
