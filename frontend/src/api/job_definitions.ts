import { apiFetch } from "./client";
import {
  type JobDefinitionResponse,
  type JobDefinitionCreate,
  type JobDefinition,
  mapJobDefinition,
} from "./types";

// ─── Job Definitions API ─────────────────────────────────────────────────────


/** Fetch all job definitions */
export async function listJobDefinitions(): Promise<JobDefinition[]> {
  const raw = await apiFetch<JobDefinitionResponse[]>("/job-definitions/");
  return raw.map(mapJobDefinition);
}

/** Fetch a single job definition by ID */
export async function getJobDefinition(id: number): Promise<JobDefinition> {
  const raw = await apiFetch<JobDefinitionResponse>(`/job-definitions/${id}`);
  return mapJobDefinition(raw);
}

/** Create a new job definition */
export async function createJobDefinition(
  data: JobDefinitionCreate
): Promise<JobDefinition> {
  const raw = await apiFetch<JobDefinitionResponse>("/job-definitions/", {
    method: "POST",
    body: JSON.stringify({
      type: data.type,
      implementation_key: data.implementation_key,
      name: data.name,
      config: data.config,
      description: data.description,
    }),
  });
  return mapJobDefinition(raw);
}

/** Delete a job definition by ID */
export async function deleteJobDefinition(id: number): Promise<void> {
  await apiFetch<void>(`/job-definitions/${id}`, { method: "DELETE" });
}

//       e.g. GET /job-definitions/implementations → string[]
//       This would let the frontend populate a dropdown of registered model
//       implementations instead of requiring free-text input.
export async function listImplementationKeys(): Promise<string[]> {
  return apiFetch<string[]>("/job-definitions/implementations");
}

//       e.g. GET /job-definitions/types → string[]
//       This would let the frontend stay in sync with backend-registered types.
export async function listJobTypes(): Promise<string[]> {
  return apiFetch<string[]>("/job-definitions/types");
}