import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Plus,
  MagnifyingGlass,
  Rows,
  Kanban,
  Globe,
  MapPin,
  Check,
  WarningCircle,
  ArrowClockwise,
} from "@phosphor-icons/react";
import { PageHeading } from "./ui";
import { useDemo } from "./store";
import { discoveryCandidates } from "./fixtures";
import { monthCost } from "./model";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  KindFilter,
  Modal,
  SearchInput,
  Status,
} from "./ui";
import { EvidenceList, OpportunityPanel } from "./OpportunityPanel";
import type { Kind, Opportunity } from "./types";

export function Discover() {
  const { state, dispatch, navigate, notify } = useDemo();
  const [kind, setKind] = useState<Kind>("client"),
    [query, setQuery] = useState(""),
    [location, setLocation] = useState("United States"),
    [source, setSource] = useState("All public sources");
  const [phase, setPhase] = useState<"idle" | "running" | "complete" | "error">(
    "idle",
  );
  const [scenario, setScenario] = useState("normal"),
    [error, setError] = useState("");
  const [results, setResults] = useState<Opportunity[]>([]),
    [inspect, setInspect] = useState<Opportunity | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  function invalidateSearch() {
    if (timer.current) clearTimeout(timer.current);
    setResults([]);
    setPhase("idle");
  }
  function search() {
    if (timer.current) clearTimeout(timer.current);
    if (monthCost(state) + 0.06 > 25) {
      setError(
        "The $25 monthly demo budget is exhausted. Reset the demo to start again.",
      );
      setPhase("error");
      return;
    }
    if (
      state.connections.find((c) => c.id === "brave")?.status !== "connected"
    ) {
      setError(
        "Brave Search is paused. Resume the demo connection before searching.",
      );
      setPhase("error");
      return;
    }
    setPhase("running");
    dispatch({ type: "cost", label: "Demo public search", amount: 0.06 });
    timer.current = setTimeout(() => {
      if (scenario === "failed") {
        setError(
          "The sample source timed out. Your existing opportunities are safe; this search can be retried.",
        );
        setPhase("error");
        return;
      }
      const next = discoveryCandidates.filter(
        (o) =>
          o.kind === kind &&
          (source === "All public sources" || o.source === source) &&
          `${o.company} ${o.title} ${o.proposed}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()) &&
          (location.trim().toLowerCase() === "united states" ||
            !location.trim() ||
            o.location.toLowerCase().includes(location.trim().toLowerCase())),
      );
      setResults(scenario === "empty" ? [] : next);
      setPhase("complete");
    }, 900);
  }
  return (
    <div className="page">
      <PageHeading
        title="Find your next opportunity."
        description="Start with a real need. Bring the right opportunities into your pipeline."
      />
      <div className="discovery-layout">
        <section>
          <div className="panel discovery-form">
            <KindFilter
              value={kind}
              onChange={(k) => {
                invalidateSearch();
                setKind(k as Kind);
                setSource("All public sources");
              }}
            />
            <div className="search-form-grid">
              <label className="field-label">
                {kind === "client"
                  ? "Company, service, or project"
                  : "Role or skill"}
                <input
                  value={query}
                  onChange={(e) => {
                    invalidateSearch();
                    setQuery(e.target.value);
                  }}
                  placeholder={
                    kind === "client"
                      ? "e.g. client intake, reporting"
                      : "e.g. automation, integrations"
                  }
                />
              </label>
              <label className="field-label">
                Location
                <input
                  value={location}
                  onChange={(e) => {
                    invalidateSearch();
                    setLocation(e.target.value);
                  }}
                  placeholder="United States"
                />
              </label>
              <label className="field-label">
                Source
                <select
                  value={source}
                  onChange={(e) => {
                    invalidateSearch();
                    setSource(e.target.value);
                  }}
                >
                  <option>All public sources</option>
                  {(kind === "client"
                    ? ["Brave Search", "Agency websites"]
                    : ["OnlineJobs", "Company careers"]
                  ).map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="discovery-form-footer">
              <span>
                <Globe size={15} /> Public-source fixtures · $0.06 demo usage
                per search
              </span>
              <Button
                variant="primary"
                onClick={search}
                disabled={phase === "running"}
              >
                <MagnifyingGlass size={17} />
                {phase === "running" ? "Researching…" : "Find opportunities"}
              </Button>
            </div>
          </div>
          <div className="results-heading">
            <h2>
              {phase === "complete"
                ? `${results.length} ${results.length === 1 ? "opportunity" : "opportunities"} found`
                : "Discovery results"}
            </h2>
            <Badge>Sample search</Badge>
          </div>
          {phase === "running" ? (
            <div
              className="skeleton-results"
              role="status"
              aria-label="Researching sample sources"
            >
              {[0, 1, 2].map((i) => (
                <div className="skeleton-row" key={i}>
                  <span />
                  <div>
                    <i />
                    <i />
                  </div>
                </div>
              ))}
            </div>
          ) : phase === "error" ? (
            <div className="panel failure-state">
              <WarningCircle size={30} />
              <h3>Research needs another try.</h3>
              <p>{error}</p>
              <Button onClick={search}>
                <ArrowClockwise size={16} />
                Retry search
              </Button>
            </div>
          ) : phase === "complete" ? (
            results.length ? (
              <div className="discovery-results">
                {results.map((o) => {
                  const added = state.opportunities.some((p) => p.id === o.id);
                  return (
                    <article className="discovery-card" key={o.id}>
                      <div className="discovery-card-top">
                        <Avatar o={o} />
                        <div>
                          <h3>{o.company}</h3>
                          <span>{o.title}</span>
                        </div>
                        <Badge tone="green">
                          {o.email ? "Contact sourced" : "Needs contact"}
                        </Badge>
                      </div>
                      <p>{o.evidence[0].text}</p>
                      <div className="result-meta">
                        <span>
                          <MapPin size={14} />
                          {o.location}
                        </span>
                        <span>
                          <Globe size={14} />
                          {o.source}
                        </span>
                      </div>
                      <div className="discovery-card-actions">
                        <Button variant="ghost" onClick={() => setInspect(o)}>
                          View research <ArrowUpRight size={15} />
                        </Button>
                        <Button
                          variant={added ? "secondary" : "primary"}
                          onClick={() => {
                            if (added) navigate("pipeline", o.id);
                            else {
                              dispatch({ type: "add", opportunity: o });
                              notify(`${o.company} added to your pipeline.`);
                            }
                          }}
                        >
                          {added ? (
                            <>
                              <Check size={15} />
                              Open in pipeline
                            </>
                          ) : (
                            <>
                              <Plus size={15} />
                              Add to pipeline
                            </>
                          )}
                        </Button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <Empty title="No matches in this sample">
                Try a broader phrase or choose all public sources. An empty
                sample result does not mean no real prospects exist.
              </Empty>
            )
          ) : (
            <div className="discovery-intro">
              <span className="large-search">
                <MagnifyingGlass size={32} weight="duotone" />
              </span>
              <h2>Good outreach starts here.</h2>
              <p>
                Search for agencies with a specific project need, or roles that
                fit your work. Review the evidence before adding an opportunity.
              </p>
              <div>
                <Badge>Published needs</Badge>
                <Badge>Source evidence</Badge>
                <Badge>Contact details</Badge>
              </div>
            </div>
          )}
        </section>
        <aside className="discovery-aside">
          <div className="panel">
            <span className="subsection-label">YOUR SEARCH BRIEF</span>
            <h3>Useful work. Clear fit.</h3>
            <p>
              US agencies and teams looking for automation, internal tools, or
              better client operations.
            </p>
            <div className="brief-rule" />
            <strong>What makes a good prospect</strong>
            <ul className="check-list">
              <li>
                <Check size={15} />A specific, published need
              </li>
              <li>
                <Check size={15} />A deliverable you can explain
              </li>
              <li>
                <Check size={15} />
                An evidenced contact route
              </li>
              <li>
                <Check size={15} />
                Relevant, honest proof
              </li>
            </ul>
          </div>
          <div className="panel demo-controls">
            <h3>Try a different outcome</h3>
            <p>Preview how the workspace handles imperfect searches.</p>
            <label className="field-label">
              Demo search result
              <select
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              >
                <option value="normal">Matching opportunities</option>
                <option value="empty">No matching results</option>
                <option value="failed">Source temporarily unavailable</option>
              </select>
            </label>
          </div>
        </aside>
      </div>
      <Modal
        open={!!inspect}
        onClose={() => setInspect(null)}
        title={inspect?.company ?? "Research"}
        description="Review the sample evidence before adding an opportunity."
        wide
      >
        {inspect && <EvidenceList o={inspect} />}
      </Modal>
    </div>
  );
}

export function Pipeline() {
  const { state, navigate, selectedId } = useDemo();
  const selected = state.opportunities.find((o) => o.id === selectedId);
  const [kind, setKind] = useState<Kind | "all">(selected?.kind ?? "client"),
    [query, setQuery] = useState(""),
    [view, setView] = useState("table"),
    [stage, setStage] = useState("all");
  useEffect(() => {
    if (selected) setKind(selected.kind);
  }, [selectedId]);
  const rows = state.opportunities.filter(
    (o) =>
      o.kind === kind &&
      `${o.company} ${o.title} ${o.contact}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (stage === "all" || o.stage === stage),
  );
  const lanes = [
    { label: "Research", stages: ["research"] },
    { label: "Review & approved", stages: ["review", "ready"] },
    { label: "In conversation", stages: ["contacted", "replied"] },
    {
      label: "Closed & needs checking",
      stages: ["needs_checking", "suppressed", "closed"],
    },
  ];
  return (
    <div className={`page pipeline-page ${selected ? "has-detail" : ""}`}>
      <PageHeading
        title="Every opportunity, in view."
        description="Keep the context. Know the next step."
      >
        <Button variant="primary" onClick={() => navigate("discover")}>
          <Plus size={17} />
          Find opportunities
        </Button>
      </PageHeading>
      <div className="pipeline-toolbar">
        <KindFilter
          value={kind}
          onChange={(k) => {
            setKind(k);
            navigate("pipeline");
          }}
        />
        <div className="toolbar-end">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="Search pipeline…"
            label="Search pipeline"
          />
          <label className="sr-only" htmlFor="stage-filter">
            Filter by status
          </label>
          <select
            id="stage-filter"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="research">Needs research</option>
            <option value="review">Ready for review</option>
            <option value="ready">Approved</option>
            <option value="contacted">Contacted / applied</option>
            <option value="replied">Replied</option>
            <option value="needs_checking">Needs checking</option>
            <option value="suppressed">Suppressed</option>
            <option value="closed">Skipped</option>
          </select>
          <div className="view-toggle" role="group" aria-label="Pipeline view">
            <button
              aria-label="Table view"
              aria-pressed={view === "table"}
              onClick={() => setView("table")}
            >
              <Rows size={18} />
            </button>
            <button
              aria-label="Board view"
              aria-pressed={view === "board"}
              onClick={() => setView("board")}
            >
              <Kanban size={18} />
            </button>
          </div>
        </div>
      </div>
      <div className={`pipeline-body ${selected ? "split-workspace" : ""}`}>
        <section className="pipeline-records">
          {rows.length ? (
            view === "table" ? (
              <div className="table-wrap">
                <table className="opportunity-table">
                  <thead>
                    <tr>
                      <th>Company / opportunity</th>
                      <th className="hide-in-split">Fit</th>
                      <th>Status</th>
                      <th className="hide-in-split">Source</th>
                      <th>
                        <span className="sr-only">Details</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((o) => (
                      <tr
                        key={o.id}
                        className={selectedId === o.id ? "selected-row" : ""}
                      >
                        <td>
                          <button
                            className="company-cell"
                            onClick={() => navigate("pipeline", o.id)}
                          >
                            <Avatar o={o} />
                            <span>
                              <strong>{o.company}</strong>
                              <small>{o.title}</small>
                            </span>
                          </button>
                        </td>
                        <td className="hide-in-split">
                          <span
                            className={`fit-label ${o.fit === "Needs research" ? "amber" : ""}`}
                          >
                            <span />
                            {o.fit}
                          </span>
                        </td>
                        <td>
                          <Status o={o} />
                        </td>
                        <td className="source-cell hide-in-split">
                          {o.source}
                        </td>
                        <td>
                          <button
                            className="plain icon-button"
                            aria-label={`View ${o.company}`}
                            onClick={() => navigate("pipeline", o.id)}
                          >
                            <ArrowUpRight size={17} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="table-footer">
                  {rows.length}{" "}
                  {kind === "client" ? "client opportunities" : "applications"}
                  <span>Fictional sample records</span>
                </div>
              </div>
            ) : (
              <div className={`board ${selected ? "compact" : ""}`}>
                {lanes.map((lane) => (
                  <section key={lane.label} className="board-lane">
                    <h2>
                      {lane.label}
                      <span>
                        {
                          rows.filter((o) => lane.stages.includes(o.stage))
                            .length
                        }
                      </span>
                    </h2>
                    {rows
                      .filter((o) => lane.stages.includes(o.stage))
                      .map((o) => (
                        <button
                          key={o.id}
                          className="board-card"
                          onClick={() => navigate("pipeline", o.id)}
                        >
                          <Avatar o={o} small />
                          <strong>{o.company}</strong>
                          <p>{o.title}</p>
                          <Status o={o} />
                        </button>
                      ))}
                    {!rows.some((o) => lane.stages.includes(o.stage)) && (
                      <span className="empty-lane">Nothing here yet</span>
                    )}
                  </section>
                ))}
              </div>
            )
          ) : (
            <Empty title="No opportunities match">
              Clear your filters or discover something new.
            </Empty>
          )}
        </section>
        {selected && (
          <OpportunityPanel
            key={selected.id}
            o={selected}
            onClose={() => navigate("pipeline")}
          />
        )}
      </div>
    </div>
  );
}
