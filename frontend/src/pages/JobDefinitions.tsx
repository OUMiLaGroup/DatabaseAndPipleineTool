import { useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { listJobDefinitions, deleteJobDefinition } from "../api/job_definitions";
import type { JobDefinition } from "../api/types";
import { DefinitionCard } from "../components/job-definitions/DefinitionCard";
import { CreateForm } from "../components/job-definitions/CreateForm";

export default function JobDefinitions() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data: definitions = [], isLoading, error } = useQuery({
    queryKey: ["job-definitions"],
    queryFn: listJobDefinitions,
    refetchInterval: 10_000,
  });

  // Optimistic delete — item vanishes instantly, restored if server errors
  const deleteMutation = useMutation({
    mutationFn: deleteJobDefinition,
    onMutate: async (id: number) => {
      await queryClient.cancelQueries({ queryKey: ["job-definitions"] });
      const snapshot = queryClient.getQueryData<JobDefinition[]>(["job-definitions"]);
      queryClient.setQueryData<JobDefinition[]>(["job-definitions"], (old = []) =>
        old.filter((d) => d.id !== id)
      );
      if (expandedId === id) setExpandedId(null);
      return { snapshot };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.snapshot) {
        queryClient.setQueryData(["job-definitions"], ctx.snapshot);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["job-definitions"] });
    },
    meta: { errorTitle: "Could not delete job definition" },
  });

  // On create, insert the real server-returned item immediately — no refetch needed
  const handleCreated = (newDef: JobDefinition) => {
    queryClient.setQueryData<JobDefinition[]>(["job-definitions"], (old = []) => [
      ...old,
      newDef,
    ]);
    queryClient.invalidateQueries({ queryKey: ["job-definitions"] });
  };

  return (
    <div className="jd-page">
      <div className="jd-page__header">
        <h1 className="jd-page__title">Job Definitions</h1>
        <p className="jd-page__subtitle">
          Manage annotation job types and their configurations
        </p>
      </div>

      <div className="jd-layout">
        {/* Left — definition list */}
        <div>
          <span className="jd-section-label">
            Existing definitions ({definitions.length})
          </span>

          {isLoading && <div className="jd-loading">Loading…</div>}

          {error && (
            <div className="jd-list-error">Failed to load definitions</div>
          )}

          {!isLoading && definitions.length === 0 && !error && (
            <div className="jd-empty">No job definitions yet</div>
          )}

          <div className="jd-card-list">
            {definitions.map((def) => (
              <DefinitionCard
                key={def.id}
                def={def}
                isExpanded={expandedId === def.id}
                onToggle={() => setExpandedId(expandedId === def.id ? null : def.id)}
                onDelete={() => deleteMutation.mutateAsync(def.id)}
              />
            ))}
          </div>
        </div>

        {/* Right — create form */}
        <CreateForm onCreated={handleCreated} />
      </div>
    </div>
  );
}
