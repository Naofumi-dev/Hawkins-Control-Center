import type { Task } from "./types";

type JobContext = {
  opportunity_id: string;
  context_version: number;
  questions: string[];
};
type ReviewedResource = {
  id: string;
  version: string;
  active: boolean;
  verified_at: string | null;
};

// Only current, complete suggestions may seed the review editor. This never
// creates a saved revision or approval; those remain server actions.
export function currentCoverLetter(
  job: JobContext,
  tasks: Task[],
  resources: ReviewedResource[],
) {
  return tasks.find((task) => {
    const result = task.result;
    return (
      task.agent === "Steve" &&
      task.task_type === "cover_letter" &&
      task.opportunity_id === job.opportunity_id &&
      task.context_version === job.context_version &&
      ["review", "done"].includes(task.status) &&
      !task.blocker &&
      !!result?.draft_body.trim() &&
      result.missing.length === 0 &&
      !!result.source_resources?.length &&
      result.source_resources.every((saved) =>
        resources.some(
          (r) =>
            r.id === saved.id &&
            r.version === saved.version &&
            r.active &&
            !!r.verified_at,
        ),
      ) &&
      JSON.stringify(result.screening_answers?.map((a) => a.question)) ===
        JSON.stringify(job.questions) &&
      result.screening_answers!.every((a) => !!a.answer.trim())
    );
  });
}
