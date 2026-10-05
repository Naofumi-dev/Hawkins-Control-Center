import { describe, expect, it } from "vitest";
import { currentCoverLetter } from "../src/jobDraft";
import type { Task } from "../src/types";

const job = {
  opportunity_id: "job-opportunity",
  context_version: 2,
  questions: ["Relevant work?"],
};
const resource = {
  id: "profile",
  version: "v1",
  active: true,
  verified_at: "2026-10-05",
};
const task: Task = {
  id: "steve",
  opportunity_id: job.opportunity_id,
  conversation_id: null,
  originating_message_id: null,
  agent: "Steve",
  task_type: "cover_letter",
  title: "Prepare letter",
  status: "review",
  blocker: null,
  context_version: 2,
  created_at: "2026-10-05",
  due_at: "2026-10-05",
  result: {
    summary: "A draft",
    evidence: [],
    missing: [],
    draft_body: "I can help your team track each intake and its next step.",
    suggested_category: "",
    screening_answers: [
      { question: "Relevant work?", answer: "Built an intake demo." },
    ],
    source_resources: [{ id: "profile", version: "v1" }],
  },
};

describe("automatic cover-letter review", () => {
  it("loads a complete current Steve draft with its answers", () => {
    expect(currentCoverLetter(job, [task], [resource])).toBe(task);
  });
  it("never uses another opportunity or an old job context", () => {
    expect(
      currentCoverLetter(
        job,
        [{ ...task, opportunity_id: "other" }],
        [resource],
      ),
    ).toBeUndefined();
    expect(
      currentCoverLetter({ ...job, context_version: 3 }, [task], [resource]),
    ).toBeUndefined();
  });
  it("holds a draft when its supporting profile changed or is no longer reviewed", () => {
    expect(
      currentCoverLetter(job, [task], [{ ...resource, version: "v2" }]),
    ).toBeUndefined();
    expect(
      currentCoverLetter(job, [task], [{ ...resource, verified_at: null }]),
    ).toBeUndefined();
    expect(
      currentCoverLetter(job, [task], [{ ...resource, active: false }]),
    ).toBeUndefined();
  });
  it("does not load blocked or incomplete suggestions", () => {
    expect(
      currentCoverLetter(job, [{ ...task, status: "blocked" }], [resource]),
    ).toBeUndefined();
    expect(
      currentCoverLetter(
        job,
        [{ ...task, result: { ...task.result!, missing: ["Availability"] } }],
        [resource],
      ),
    ).toBeUndefined();
  });
  it("rejects answers for different job questions and untracked legacy suggestions", () => {
    expect(
      currentCoverLetter(
        { ...job, questions: ["Availability?"] },
        [task],
        [resource],
      ),
    ).toBeUndefined();
    expect(
      currentCoverLetter(
        job,
        [{ ...task, result: { ...task.result!, source_resources: undefined } }],
        [resource],
      ),
    ).toBeUndefined();
  });
  it("does not treat Eleven's findings as Steve's cover letter", () => {
    expect(
      currentCoverLetter(
        job,
        [{ ...task, agent: "Eleven", task_type: "qualify_job" }],
        [resource],
      ),
    ).toBeUndefined();
  });
});
