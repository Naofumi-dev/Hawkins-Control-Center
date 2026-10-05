import { useEffect, useRef, useState } from "react";
import {
  SquaresFour,
  MagnifyingGlass,
  Kanban,
  NotePencil,
  EnvelopeSimple,
  Books,
  PlugsConnected,
  ArrowUpRight,
  ArrowClockwise,
  List,
  Check,
  type Icon,
} from "@phosphor-icons/react";
import { useDemo } from "./store";
import { Button, Modal, Avatar, Status } from "./ui";
import type { Page } from "./types";
import { currentRevision } from "./model";
import { Today } from "./Today";
import { Discover, Pipeline } from "./Workspaces";
import { DraftStudio } from "./DraftStudio";
import { Inbox, Library, Connections } from "./Integrations";

const navigation: { id: Page; label: string; icon: Icon; section?: string }[] =
  [
    { id: "today", label: "Today", icon: SquaresFour, section: "WORKSPACE" },
    { id: "discover", label: "Discover", icon: MagnifyingGlass },
    { id: "pipeline", label: "Pipeline", icon: Kanban },
    { id: "drafts", label: "Draft Studio", icon: NotePencil },
    { id: "inbox", label: "Inbox", icon: EnvelopeSimple },
    { id: "library", label: "Library", icon: Books, section: "YOUR TOOLKIT" },
    { id: "connections", label: "Connections", icon: PlugsConnected },
  ];

export function App() {
  const { page, selectedId, navigate, state, dispatch, notify } = useDemo();
  const [searchOpen, setSearchOpen] = useState(false),
    [query, setQuery] = useState(""),
    [menu, setMenu] = useState(false),
    [reset, setReset] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0, behavior: "instant" });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [page, selectedId]);
  const draftCount = state.opportunities.filter(
    (o) => o.stage === "review",
  ).length;
  const replyCount = state.opportunities.filter(
    (o) => o.inboxState === "reply",
  ).length;
  const go = (p: Page, id?: string) => {
    navigate(p, id);
    setMenu(false);
    setSearchOpen(false);
  };
  const nav = (
    <>
      <div className="workspace-switch">
        <span className="workspace-avatar">AV</span>
        <div>
          <strong>Personal workspace</strong>
          <span>Armageddon Vivas</span>
        </div>
        <span className="private-label">Private</span>
      </div>
      <nav aria-label="Main navigation">
        {navigation.map(({ id, label, icon: Icon, section }) => (
          <div key={id}>
            {section && <div className="nav-section">{section}</div>}
            <button
              className={`nav-item ${page === id ? "active" : ""}`}
              aria-current={page === id ? "page" : undefined}
              onClick={() => go(id)}
            >
              <Icon size={19} weight={page === id ? "duotone" : "regular"} />
              <span>{label}</span>
              {id === "drafts" && draftCount > 0 && (
                <span className="nav-count">{draftCount}</span>
              )}
              {id === "inbox" && replyCount > 0 && (
                <span className="nav-count neutral">{replyCount}</span>
              )}
              {id === "connections" &&
                state.connections.some((c) => c.status === "attention") && (
                  <span
                    className="nav-alert"
                    aria-label="Connection needs attention"
                  />
                )}
            </button>
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="demo-note">
          <span className="demo-dot" />
          <strong>Demo workspace</strong>
          <p>
            Fictional records.
            <br />
            Actions stay in this browser.
          </p>
        </div>
        <button
          className="reset-link"
          onClick={() => {
            setMenu(false);
            setReset(true);
          }}
        >
          <ArrowClockwise size={15} /> Reset demo
        </button>
        <div className="user-line">
          <span className="user-avatar">A</span>
          <div>
            <strong>Armageddon Vivas</strong>
            <span>Personal account</span>
          </div>
          <Check size={14} />
        </div>
      </div>
    </>
  );
  const matches = state.opportunities.filter((o) =>
    `${o.company} ${o.title} ${currentRevision(o)?.subject ?? ""} ${currentRevision(o)?.body ?? ""}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <SquaresFour size={23} weight="fill" />
          </span>
          <span>
            hawkins<span className="brand-period">.</span>
            <small>CONTROL CENTER</small>
          </span>
        </div>
        {nav}
      </aside>
      <div className="app-main">
        <header className="topbar">
          <Button
            variant="ghost"
            className="mobile-menu icon-button"
            aria-label="Open navigation"
            onClick={() => setMenu(true)}
          >
            <List size={23} />
          </Button>
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="slash">/</span>
            <strong>{navigation.find((n) => n.id === page)?.label}</strong>
          </div>
          <div className="topbar-right">
            <button
              className="global-search-trigger"
              onClick={() => setSearchOpen(true)}
              aria-label="Search workspace"
            >
              <MagnifyingGlass size={16} />
              <span>Search anything…</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="demo-top">
              <span /> Demo
            </span>
            <span className="topbar-avatar" aria-label="Armageddon Vivas">
              AV
            </span>
          </div>
        </header>
        <main className="workspace" ref={mainRef} id="main-content">
          {page === "today" ? (
            <Today />
          ) : page === "discover" ? (
            <Discover />
          ) : page === "pipeline" ? (
            <Pipeline />
          ) : page === "drafts" ? (
            <DraftStudio />
          ) : page === "inbox" ? (
            <Inbox />
          ) : page === "library" ? (
            <Library />
          ) : (
            <Connections />
          )}
        </main>
      </div>
      <Modal
        open={menu}
        onClose={() => setMenu(false)}
        title="Hawkins"
        description="Navigate your workspace"
      >
        {nav}
      </Modal>
      <Modal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        title="Search your workspace"
        description="Find opportunities and their saved drafts."
        wide
      >
        <label className="command-search">
          <MagnifyingGlass size={21} />
          <span className="sr-only">Search opportunities and drafts</span>
          <input
            data-autofocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Company, role, subject, or draft text…"
          />
        </label>
        <div className="search-results">
          {matches.length ? (
            matches.map((o) => (
              <button
                key={o.id}
                className="search-result"
                onClick={() => go("pipeline", o.id)}
              >
                <Avatar o={o} small />
                <div>
                  <strong>{o.company}</strong>
                  <span>{o.title}</span>
                </div>
                <Status o={o} />
                <ArrowUpRight size={17} />
              </button>
            ))
          ) : (
            <p className="quiet">No matches. Try a company name or role.</p>
          )}
        </div>
      </Modal>
      <Modal
        open={reset}
        onClose={() => setReset(false)}
        title="Start with a fresh workspace?"
        description="This clears your local edits and restores the twelve sample opportunities."
      >
        <div className="modal-actions">
          <Button onClick={() => setReset(false)}>Keep my changes</Button>
          <Button
            variant="primary"
            onClick={() => {
              dispatch({ type: "reset" });
              setReset(false);
              navigate("today");
              notify("Demo restored. Your sample workspace is ready.");
            }}
          >
            Reset demo
          </Button>
        </div>
      </Modal>
    </div>
  );
}
