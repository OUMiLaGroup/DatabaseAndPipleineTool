import { useState } from "react";
import { createJobDefinition } from "../../api/job_definitions";
import type { JobDefinition, JobDefinitionCreate, JobType } from "../../api/types";
import { ConfigEditor } from "./ConfigEditor";
import { ErrorNotice } from "../ErrorNotice";

// ─── CreateForm ───────────────────────────────────────────────────────────────

export function CreateForm({ onCreated }: { onCreated: (def: JobDefinition) => void }) {
  const [name, setName] = useState("");
  const [jobType, setJobType] = useState<JobType>("object_detection");
  const [implKey, setImplKey] = useState("");
  const [description, setDescription] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [showInfo, setShowInfo] = useState(false);

  const canSubmit = Boolean(name.trim() && implKey.trim() && !submitting);

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    // Attempt to JSON-parse each value; fall back to string
    const parsedConfig: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(config)) {
      if (!k.trim()) continue;
      try { parsedConfig[k] = JSON.parse(v); }
      catch { parsedConfig[k] = v; }
    }

    const payload: JobDefinitionCreate = {
      type: jobType,
      implementation_key: implKey,
      name: name.trim(),
      config: parsedConfig,
      description: description.trim(),
    };

    try {
      const result = await createJobDefinition(payload);
      setName("");
      setImplKey("");
      setDescription("");
      setConfig({});
      onCreated(result);
    } catch (err: unknown) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="jd-create-card">
      <div className="jd-create-card__header">
        <div className="jd-create-card__title-row">
          <div className="jd-create-card__title">New Job Definition</div>
          <button
            type="button"
            className="jd-info-btn"
            aria-label="Show setup info"
            aria-expanded={showInfo}
            onClick={() => setShowInfo((v) => !v)}
          >
            i
          </button>
        </div>
        <div className="jd-create-card__subtitle">
          Define a new annotation job type for routes
        </div>
      </div>

      <div className="jd-create-card__body">
        <div>
          <label className="jd-label">Job type</label>
          <select className="jd-input" value={jobType} onChange={(e) => {
            const selected = e.target.value as JobType;
            setJobType(selected);
            if (selected === "depth") {
              setName("Monocular Depth (DA3)");
              setImplKey("depth_anything_3");
              setDescription("Pixel depth aligned to original images. Add camera calibration for meters.");
              setConfig({ device: '"auto"', process_res: "504", calibrations: "{}", require_metric: "false" });
            } else {
              setName(""); setImplKey(""); setDescription(""); setConfig({});
            }
          }}>
            <option value="object_detection">Object Detection</option>
            <option value="depth">Pixel Depth (Depth Anything 3)</option>
          </select>
        </div>
        {jobType === "depth" && <div className="jd-info-panel">
          Export saves one NPZ depth map per image and a data.json index. Distances in meters require
          calibration for the selected camera: width, height, fx and fy in pixels at the original image resolution.
          Enter these under calibrations, for example {`{"front_regular":{"width":YOUR_WIDTH,"height":YOUR_HEIGHT,"fx":YOUR_FX,"fy":YOUR_FY}}`}.
          Without calibration, values are focal-normalized and cannot be read as meters.
          Set require_metric to true to reject jobs without calibration. CPU processing can take a long time.
        </div>}
        {showInfo && (
          <div className="jd-info-panel">
            Implementation Key is the name of the Python class that runs the job, and Config holds the parameters passed to that class (e.g. detection transformers need a model name).
          </div>
        )}

        {/* Name */}
        <div>
          <label className="jd-label">Name *</label>
          <input
            className="jd-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. YOLOv8 Object Detection"
          />
        </div>

        {/* Implementation Key */}
        <div>
          <label className="jd-label">Implementation Key *</label>
          <input
            className="jd-input"
            value={implKey}
            onChange={(e) => setImplKey(e.target.value)}
            placeholder="e.g. YOLOv8Detector"
          />
        </div>

        {/* Description */}
        <div>
          <label className="jd-label">Description</label>
          <textarea
            className="jd-input jd-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what this job definition does..."
          />
        </div>

        {/* Config */}
        <ConfigEditor config={config} onChange={setConfig} />

        {/* Error */}
        {error != null && <ErrorNotice error={error} title="Could not create job definition" />}

        {/* Submit */}
        <button
          className="jd-btn jd-btn--submit"
          onClick={handleSubmit}
          disabled={!canSubmit}
          data-submitting={submitting}
        >
          {submitting ? "Creating…" : "Create Definition"}
        </button>
      </div>
    </div>
  );
}
