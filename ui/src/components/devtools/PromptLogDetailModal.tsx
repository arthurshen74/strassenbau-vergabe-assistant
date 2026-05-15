// Full-detail modal for a single PromptExecutionLog entry.
// Opened from PromptLogDrawer when the user clicks a list item.

import { useState } from 'react';
import {
  ChevronDownIcon,
  ChevronRightIcon,
  XMarkIcon,
} from '@heroicons/react/20/solid';
import * as Headless from '@headlessui/react';
import { usePromptExecutionLog } from '../../api/prompt_execution_logs';
import type { PromptExecutionLogDetailDTO } from '../../types/generated';

// ---------------------------------------------------------------------------
// Small collapsible/expandable section used throughout this modal.
// ---------------------------------------------------------------------------
function Section({
  title,
  defaultOpen = false,
  badge,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-md border border-zinc-200 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:text-zinc-300 dark:hover:bg-zinc-800"
      >
        {open ? (
          <ChevronDownIcon className="h-4 w-4 shrink-0 text-zinc-400" />
        ) : (
          <ChevronRightIcon className="h-4 w-4 shrink-0 text-zinc-400" />
        )}
        {title}
        {badge && <span className="ml-auto">{badge}</span>}
      </button>
      {open && <div className="border-t border-zinc-200 dark:border-zinc-700">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// A read-only textarea for displaying large blobs (system prompt, JSON, etc.)
// ---------------------------------------------------------------------------
function CodeArea({
  value,
  rows = 10,
}: {
  value: string;
  rows?: number;
}) {
  return (
    <textarea
      readOnly
      value={value}
      rows={rows}
      className="w-full resize-y rounded-none bg-zinc-50 px-3 py-2 font-mono text-xs text-zinc-800 focus:outline-none dark:bg-zinc-900 dark:text-zinc-200"
    />
  );
}

// ---------------------------------------------------------------------------
// Renders a single message from the messages array.
// ---------------------------------------------------------------------------
function MessageRow({ msg }: { msg: Record<string, unknown> }) {
  const role = typeof msg.role === 'string' ? msg.role : 'unknown';
  const roleColor: Record<string, string> = {
    user: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    assistant:
      'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    tool: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    system:
      'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300',
  };
  const colorClass =
    roleColor[role] ??
    'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300';

  // Content might be a string or a complex object (e.g. tool result).
  const content =
    typeof msg.content === 'string'
      ? msg.content
      : JSON.stringify(msg.content, null, 2);

  // If there are tool_calls embedded in an assistant message, show them.
  const toolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : null;

  return (
    <div className="border-b border-zinc-100 px-3 py-2 last:border-b-0 dark:border-zinc-800">
      <span
        className={`mb-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${colorClass}`}
      >
        {role}
      </span>
      {content && (
        <p className="whitespace-pre-wrap font-mono text-xs text-zinc-700 dark:text-zinc-300">
          {content}
        </p>
      )}
      {toolCalls && (
        <pre className="mt-1 whitespace-pre-wrap font-mono text-xs text-zinc-500 dark:text-zinc-400">
          {JSON.stringify(toolCalls, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tool tree — renders each tool entry from the catalog.
// ---------------------------------------------------------------------------
function ToolTree({ tools }: { tools: Record<string, unknown>[] }) {
  return (
    <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
      {tools.map((tool, i) => {
        const fn =
          typeof tool.function === 'object' && tool.function !== null
            ? (tool.function as Record<string, unknown>)
            : null;
        const name =
          fn && typeof fn.name === 'string' ? fn.name : `tool_${i}`;
        const description =
          fn && typeof fn.description === 'string' ? fn.description : '';
        return (
          <details key={i} className="group">
            <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:text-zinc-300 dark:hover:bg-zinc-800">
              <span className="mr-2 text-zinc-400 group-open:hidden">▶</span>
              <span className="mr-2 hidden text-zinc-400 group-open:inline">▼</span>
              <code className="font-mono">{name}</code>
              {description && (
                <span className="ml-2 font-normal text-zinc-400">
                  — {description}
                </span>
              )}
            </summary>
            <div className="border-t border-zinc-100 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900">
              <CodeArea
                value={JSON.stringify(fn ?? tool, null, 2)}
                rows={6}
              />
            </div>
          </details>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main modal body once data is loaded.
// ---------------------------------------------------------------------------
function DetailBody({ log }: { log: PromptExecutionLogDetailDTO }) {
  const sentAt = new Date(log.sent_at);
  const returnedAt = new Date(log.returned_at);

  return (
    <div className="flex flex-col gap-3">
      {/* ── Timing & metrics ── */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 rounded-md bg-zinc-50 px-4 py-3 text-sm dark:bg-zinc-800/50">
        <div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Sent</span>
          <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
            {sentAt.toLocaleString()}
          </p>
        </div>
        <div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Returned</span>
          <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
            {returnedAt.toLocaleString()}
          </p>
        </div>
        <div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Duration</span>
          <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
            {log.duration_ms.toLocaleString()} ms
          </p>
        </div>
        <div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            Tokens in / out
          </span>
          <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
            {log.tokens_in ?? '—'} / {log.tokens_out ?? '—'}
          </p>
        </div>
        <div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Model</span>
          <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
            {log.model_name}
          </p>
        </div>
        <div>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            temp / top_p{log.min_p !== null ? ' / min_p' : ''}
          </span>
          <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
            {log.temperature} / {log.top_p}
            {log.min_p !== null ? ` / ${log.min_p}` : ''}
          </p>
        </div>
        {log.finish_reason && (
          <div>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              Finish reason
            </span>
            <p className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
              {log.finish_reason}
            </p>
          </div>
        )}
      </div>

      {/* ── Provider URL ── */}
      <div className="rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-700">
        <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
          Provider URL
        </p>
        <code className="break-all text-xs text-zinc-800 dark:text-zinc-200">
          {log.provider_url}
        </code>
      </div>

      {/* ── Headers (collapsible) ── */}
      <Section title="Headers">
        <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {Object.entries(log.request_headers).map(([k, v]) => (
            <div key={k} className="flex items-start gap-3 px-3 py-1.5">
              <code className="w-48 shrink-0 text-xs text-zinc-500 dark:text-zinc-400">
                {k}
              </code>
              <code className="break-all text-xs text-zinc-800 dark:text-zinc-200">
                {v}
              </code>
            </div>
          ))}
        </div>
      </Section>

      {/* ── System prompt (expandable) ── */}
      <Section title="System Prompt" defaultOpen>
        <CodeArea value={log.system_prompt} rows={12} />
      </Section>

      {/* ── Structured output schema (if exists) ── */}
      {log.response_format && (
        <Section title="Structured Output Schema" defaultOpen>
          <CodeArea
            value={JSON.stringify(log.response_format, null, 2)}
            rows={10}
          />
        </Section>
      )}

      {/* ── Tool catalog (expandable tree) ── */}
      {log.tools && log.tools.length > 0 && (
        <Section
          title="Tool Catalog"
          badge={
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-zinc-700 dark:text-zinc-400">
              {log.tools.length}
            </span>
          }
        >
          <ToolTree tools={log.tools} />
        </Section>
      )}

      {/* ── Messages ── */}
      <Section
        title="Messages"
        defaultOpen
        badge={
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-zinc-700 dark:text-zinc-400">
            {log.messages.length}
          </span>
        }
      >
        <div>
          {log.messages.map((m, i) => (
            <MessageRow key={i} msg={m as Record<string, unknown>} />
          ))}
        </div>
      </Section>

      {/* ── Response ── */}
      <Section title="Response" defaultOpen>
        <div className="p-3">
          {log.response_text && !log.response_structured && (
            <CodeArea value={log.response_text} rows={8} />
          )}
          {log.response_structured && (
            <CodeArea
              value={JSON.stringify(log.response_structured, null, 2)}
              rows={10}
            />
          )}
          {log.response_tool_calls && log.response_tool_calls.length > 0 && (
            <div className={log.response_text || log.response_structured ? 'mt-3' : ''}>
              <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Tool calls
              </p>
              <CodeArea
                value={JSON.stringify(log.response_tool_calls, null, 2)}
                rows={8}
              />
            </div>
          )}
          {!log.response_text &&
            !log.response_structured &&
            (!log.response_tool_calls || log.response_tool_calls.length === 0) && (
              <p className="text-xs text-zinc-400">(no response content)</p>
            )}
        </div>
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component.
// ---------------------------------------------------------------------------
export function PromptLogDetailModal({
  logId,
  open,
  onClose,
}: {
  logId: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading, isError } = usePromptExecutionLog(
    logId ?? undefined,
  );

  return (
    <Headless.Dialog open={open} onClose={onClose} className="relative z-50">
      <Headless.DialogBackdrop className="fixed inset-0 bg-zinc-950/40 backdrop-blur-sm transition duration-150 data-closed:opacity-0" />

      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-start justify-center p-4 sm:p-8">
          <Headless.DialogPanel className="w-full max-w-4xl rounded-xl bg-white shadow-2xl ring-1 ring-zinc-950/5 transition duration-150 data-closed:scale-95 data-closed:opacity-0 dark:bg-zinc-900 dark:ring-white/10">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
              <div>
                <Headless.DialogTitle className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                  Prompt Execution Detail
                </Headless.DialogTitle>
                {data && (
                  <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                    <span className="font-medium text-zinc-700 dark:text-zinc-300">
                      {data.prompt_name}
                    </span>{' '}
                    · v{data.prompt_version} ·{' '}
                    <span className="font-mono text-xs">{data.prompt_type}</span>
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="max-h-[80vh] overflow-y-auto px-6 py-4">
              {isLoading && (
                <p className="text-sm text-zinc-500">Loading…</p>
              )}
              {isError && (
                <p className="text-sm text-red-600 dark:text-red-400">
                  Failed to load log details.
                </p>
              )}
              {data && <DetailBody log={data} />}
            </div>
          </Headless.DialogPanel>
        </div>
      </div>
    </Headless.Dialog>
  );
}
