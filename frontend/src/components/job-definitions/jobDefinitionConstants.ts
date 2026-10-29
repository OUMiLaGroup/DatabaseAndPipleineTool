import type { JobType } from "../../api/types";

export const JOB_TYPES: JobType[] = ["object_detection", "lane_detection", "segmentation", "depth"];

export const TYPE_LABELS: Record<JobType, string> = {
  object_detection: "Object Detection",
  lane_detection:   "Lane Detection",
  segmentation:     "Segmentation",
  depth: "Pixel Depth",
};

export const TYPE_COLORS: Record<JobType, string> = {
  object_detection: "var(--class-vehicle)",
  lane_detection:   "var(--class-lane-line)",
  segmentation:     "var(--accent-cvat)",
  depth: "var(--accent-cvat)",
};
