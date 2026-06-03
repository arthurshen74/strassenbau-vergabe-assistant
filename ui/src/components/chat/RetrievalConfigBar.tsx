// Project-chat retrieval controls: modality (Simple/Plus) + the optional RAG stages. Shown above
// the chat input for project chats only. State lives in the per-conversation retrieval-config store.

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
};

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <span className="flex items-center gap-1.5">
      <Checkbox color="blue" checked={checked} onChange={onChange} />
      <span className="text-zinc-600 dark:text-zinc-300">{label}</span>
    </span>
  );
}

export function RetrievalConfigBar({ conversationId }: { conversationId: string }) {
  const config = useRetrievalConfig(conversationId);
  const setConfig = useRetrievalConfigStore((s) => s.setConfig);

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
        onChange={(v) => setConfig(conversationId, { multi_query: v })}
      />
      <Toggle
        label="BM25"
        checked={config.use_bm25}
        onChange={(v) => setConfig(conversationId, { use_bm25: v })}
      />
      <Toggle
        label="Cross-encoder"
        checked={config.use_cross_encoder}
        onChange={(v) => setConfig(conversationId, { use_cross_encoder: v })}
      />
    </div>
  );
}
