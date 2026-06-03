// Project-chat retrieval controls: modality + the optional RAG stages. Shown above the
// chat input for project chats only. LANGCHAIN is agentic and ignores the stage toggles,
// so they're disabled for it. State lives in the per-conversation retrieval-config store.

import clsx from 'clsx';
import { Select } from '../ui/select';
import { Checkbox } from '../ui/checkbox';
import {
  MODALITY_OPTIONS,
  useRetrievalConfig,
  useRetrievalConfigStore,
  type RetrievalModality,
} from '../../store/retrievalConfig';

const MODALITY_LABELS: Record<RetrievalModality, string> = {
  SIMPLE: 'Simple',
  PLUS: 'Plus',
  LANGCHAIN: 'LangChain',
};

function Toggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <span className={clsx('flex items-center gap-1.5', disabled && 'opacity-40')}>
      <Checkbox color="blue" checked={checked} disabled={disabled} onChange={onChange} />
      <span className="text-zinc-600 dark:text-zinc-300">{label}</span>
    </span>
  );
}

export function RetrievalConfigBar({ conversationId }: { conversationId: string }) {
  const config = useRetrievalConfig(conversationId);
  const setConfig = useRetrievalConfigStore((s) => s.setConfig);
  const togglesDisabled = config.modality === 'LANGCHAIN';

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-zinc-950/5 px-4 py-2 text-xs dark:border-white/5">
      <label className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400">
        Retrieval
        <Select
          value={config.modality}
          onChange={(e) =>
            setConfig(conversationId, {
              modality: e.target.value as RetrievalModality,
            })
          }
          className="!w-32"
        >
          {MODALITY_OPTIONS.map((m) => (
            <option key={m} value={m}>
              {MODALITY_LABELS[m]}
            </option>
          ))}
        </Select>
      </label>
      <Toggle
        label="Multi-query"
        checked={config.multi_query}
        disabled={togglesDisabled}
        onChange={(v) => setConfig(conversationId, { multi_query: v })}
      />
      <Toggle
        label="BM25"
        checked={config.use_bm25}
        disabled={togglesDisabled}
        onChange={(v) => setConfig(conversationId, { use_bm25: v })}
      />
      <Toggle
        label="Cross-encoder"
        checked={config.use_cross_encoder}
        disabled={togglesDisabled}
        onChange={(v) => setConfig(conversationId, { use_cross_encoder: v })}
      />
    </div>
  );
}
