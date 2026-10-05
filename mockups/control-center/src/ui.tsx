import * as Dialog from "@radix-ui/react-dialog";
import { useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import {
  ArrowRight,
  CheckCircle,
  FileText,
  X,
  MagnifyingGlass,
  EnvelopeSimple,
  Table,
  Notebook,
  FolderSimple,
  PaperPlaneTilt,
  FlowArrow,
  Globe,
  type Icon,
} from "@phosphor-icons/react";
import type { Kind, Opportunity, Resource } from "./types";
import { statusLabel } from "./model";
export function Button({
  children,
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button className={`btn ${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Avatar({
  o,
  small = false,
}: {
  o: Opportunity;
  small?: boolean;
}) {
  return (
    <span
      className={`company-avatar ${o.color} ${small ? "small" : ""}`}
      aria-hidden="true"
    >
      {o.initials}
    </span>
  );
}
export function Status({ o }: { o: Opportunity }) {
  return (
    <Badge
      tone={
        o.stage === "review"
          ? "blue"
          : ["ready", "replied"].includes(o.stage)
            ? "green"
            : ["research", "needs_checking"].includes(o.stage)
              ? "amber"
              : "neutral"
      }
    >
      <span className="status-dot" />
      {statusLabel(o)}
    </Badge>
  );
}
export function Segments<T extends string>({
  value,
  onChange,
  options,
  label = "Filter",
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; count?: number }[];
  label?: string;
}) {
  return (
    <div className="segments" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          aria-pressed={value === o.value}
          className={value === o.value ? "selected" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count !== undefined && <span>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
export function KindFilter({
  value,
  onChange,
  all = false,
}: {
  value: Kind | "all";
  onChange: (value: Kind | "all") => void;
  all?: boolean;
}) {
  return (
    <Segments
      value={value}
      onChange={onChange}
      options={[
        ...(all ? [{ value: "all" as const, label: "All work" }] : []),
        { value: "client", label: "Clients" },
        { value: "job", label: "Applications" },
      ]}
      label="Opportunity type"
    />
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <CheckCircle size={28} />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  label = "Search",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  label?: string;
}) {
  return (
    <label className="search-input">
      <MagnifyingGlass size={17} />
      <span className="sr-only">{label}</span>
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const previous = useRef<HTMLElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          ref={contentRef}
          className={`modal ${wide ? "wide" : ""}`}
          onOpenAutoFocus={(event) => {
            previous.current = document.activeElement as HTMLElement;
            const field =
              contentRef.current?.querySelector<HTMLInputElement>(
                "[data-autofocus]",
              );
            if (field) {
              event.preventDefault();
              field.focus();
            }
          }}
          onCloseAutoFocus={(e) => {
            if (previous.current?.isConnected) {
              e.preventDefault();
              previous.current.focus();
            }
          }}
        >
          <div className="modal-heading">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description>{description}</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button
                variant="ghost"
                className="icon-button"
                aria-label="Close dialog"
              >
                <X size={20} />
              </Button>
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export const toolIcons: Record<string, Icon> = {
  gmail: EnvelopeSimple,
  sheets: Table,
  notion: Notebook,
  drive: FolderSimple,
  telegram: PaperPlaneTilt,
  n8n: FlowArrow,
  brave: Globe,
};
export function ToolIcon({ id, size = 18 }: { id: string; size?: number }) {
  const Icon = toolIcons[id] ?? FileText;
  return (
    <span className={`tool-icon ${id}`}>
      <Icon size={size} weight="duotone" />
    </span>
  );
}
export function RelativeTime({ value }: { value: string }) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  return (
    <time dateTime={value}>
      {minutes < 1
        ? "Just now"
        : minutes < 60
          ? `${minutes}m ago`
          : minutes < 1440
            ? `${Math.floor(minutes / 60)}h ago`
            : `${Math.floor(minutes / 1440)}d ago`}
    </time>
  );
}
export function ResourcePreview({
  resource,
  onClose,
  action,
}: {
  resource: Resource | null;
  onClose: () => void;
  action?: ReactNode;
}) {
  return (
    <Modal
      open={!!resource}
      onClose={onClose}
      title={resource?.title ?? "Reference"}
      description={`${resource?.provider ?? ""} · Local sample document`}
    >
      <div className="document-preview">
        {resource?.preview && <Badge tone="amber">Prototype / preview</Badge>}
        <pre>{resource?.content}</pre>
      </div>
      {action && <div className="modal-actions">{action}</div>}
    </Modal>
  );
}
export function SectionHeading({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <h2>{children}</h2>
      {action}
    </div>
  );
}
export function TextLink({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className="text-link" onClick={onClick}>
      {children}
      <ArrowRight size={14} />
    </button>
  );
}

export function PageHeading({
  title,
  description,
  children,
  eyebrow,
}: {
  title: string;
  description: string;
  children?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}
