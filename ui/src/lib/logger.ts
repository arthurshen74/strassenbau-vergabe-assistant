// Channeled console logger.
//
// Browser DevTools is the right place to look for frontend traces — but
// raw console.log scattered across modules turns into noise. This wraps
// console.log in named channels (dispatcher, tool, api, sse) so each
// log line gets a colored CSS prefix you can filter on, and the whole
// thing toggles via `localStorage.debug`.
//
// Toggle from DevTools:
//   localStorage.debug = '*';                 // all channels
//   localStorage.debug = 'tool,api';          // only those two
//   localStorage.removeItem('debug');         // off (prod default)
// Then reload — the enabled set is read once at module load.
//
// Group helpers return an `end` closure rather than a global `end()`
// so nested groups (dispatcher turn containing several tool calls)
// can't accidentally close the wrong frame when a channel is off.

type Channel = 'dispatcher' | 'tool' | 'api' | 'sse';

const STYLES: Record<Channel, string> = {
  dispatcher: 'color:#9333ea;font-weight:bold',
  tool: 'color:#0ea5e9;font-weight:bold',
  api: 'color:#10b981;font-weight:bold',
  sse: 'color:#f59e0b;font-weight:bold',
};

const ALL_CHANNELS: readonly Channel[] = ['dispatcher', 'tool', 'api', 'sse'];

function readEnabled(): Set<Channel> {
  let raw: string | null = null;
  try {
    raw =
      typeof localStorage !== 'undefined'
        ? localStorage.getItem('debug')
        : null;
  } catch {
    // localStorage can throw in cross-origin / disabled-storage contexts.
    raw = null;
  }
  if (raw == null) {
    return import.meta.env.PROD ? new Set() : new Set(ALL_CHANNELS);
  }
  if (raw === '*' || raw === 'all') return new Set(ALL_CHANNELS);
  const parts = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return new Set(parts.filter((p): p is Channel => (ALL_CHANNELS as readonly string[]).includes(p)));
}

const enabled = readEnabled();

function isOn(c: Channel): boolean {
  return enabled.has(c);
}

const NOOP_END = () => {};

interface ChannelLogger {
  (...args: unknown[]): void;
  error: (...args: unknown[]) => void;
}

function makeChannel(c: Channel): ChannelLogger {
  const fn = ((...args: unknown[]) => {
    if (!isOn(c)) return;
    console.log(`%c[${c}]`, STYLES[c], ...args);
  }) as ChannelLogger;
  // Errors fire regardless of channel toggle — if something exploded,
  // a debug flag should not hide it.
  fn.error = (...args: unknown[]) => {
    console.error(`%c[${c}]`, STYLES[c], ...args);
  };
  return fn;
}

export const log = {
  dispatcher: makeChannel('dispatcher'),
  tool: makeChannel('tool'),
  api: makeChannel('api'),
  sse: makeChannel('sse'),
  group: {
    dispatcher(label: string, ...args: unknown[]): () => void {
      if (!isOn('dispatcher')) return NOOP_END;
      console.groupCollapsed(
        `%c[dispatcher] ${label}`,
        STYLES.dispatcher,
        ...args,
      );
      return () => console.groupEnd();
    },
    tool(name: string, callId: string): () => void {
      if (!isOn('tool')) return NOOP_END;
      console.groupCollapsed(
        `%c[tool: ${name}]`,
        STYLES.tool,
        callId,
      );
      return () => console.groupEnd();
    },
  },
};
