import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  useState,
  type Dispatch,
  type ReactNode,
} from "react";
import { loadState, reducer, STORAGE_KEY } from "./model";
import type { Action, Page, State } from "./types";

const pages: Page[] = [
  "today",
  "discover",
  "pipeline",
  "drafts",
  "inbox",
  "library",
  "connections",
];
function route() {
  const [page, id] = location.hash.replace(/^#\/?/, "").split("/");
  return {
    page: pages.includes(page as Page) ? (page as Page) : ("today" as Page),
    selectedId: id || "",
  };
}
type Context = {
  state: State;
  dispatch: Dispatch<Action>;
  page: Page;
  selectedId: string;
  navigate: (page: Page, id?: string) => void;
  notify: (text: string) => void;
};
const DemoContext = createContext<Context | null>(null);
export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, loadState);
  const [locationState, setLocationState] = useState(route);
  const [toast, setToast] = useState("");
  const [storageError, setStorageError] = useState(false);
  useEffect(() => {
    const handle = () => setLocationState(route());
    window.addEventListener("hashchange", handle);
    return () => window.removeEventListener("hashchange", handle);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }, [state]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(timer);
  }, [toast]);
  const navigate = (page: Page, id = "") => {
    const hash = `#/${page}${id ? "/" + id : ""}`;
    if (location.hash === hash) setLocationState(route());
    else location.hash = hash;
  };
  return (
    <DemoContext.Provider
      value={{
        state,
        dispatch,
        ...locationState,
        navigate,
        notify: (text) => setToast(text),
      }}
    >
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toast && <div className="toast">{toast}</div>}
        {storageError && (
          <div className="toast error">
            Browser storage is unavailable. Changes will last only for this
            session.
          </div>
        )}
      </div>
    </DemoContext.Provider>
  );
}
export function useDemo() {
  const context = useContext(DemoContext);
  if (!context) throw new Error("DemoProvider is required");
  return context;
}
