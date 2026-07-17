// NLP analysis modal (graded-project requirement 1): pick a prose document,
// explore its reflowed text, sentence segmentation with displacy renders, and
// POS distribution. Block-type toggles re-run the analysis with a different
// include list — watching the sentence view change is the point.

import { useState } from 'react';

import {
  useNlpAnalysis,
  useNlpDocuments,
  useNlpDocumentText,
  type BlockType,
} from '../../api/nlp';
import { Checkbox, CheckboxField } from '../../components/ui/checkbox';
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { Label } from '../../components/ui/fieldset';
import { Select } from '../../components/ui/select';
import { LoadingState } from '../../components/feedback/LoadingState';
import {
  BLOCK_TYPE_LABELS,
  DEFAULT_INCLUDE_BLOCKS,
  SELECTABLE_BLOCK_TYPES,
} from './blockTypes';
import { EntitiesTab } from './EntitiesTab';
import { PosTab } from './PosTab';
import { SentencesTab } from './SentencesTab';
import { TextTab } from './TextTab';

type Tab = 'text' | 'sentences' | 'pos' | 'entities';

const TABS: { id: Tab; name: string }[] = [
  { id: 'text', name: 'Text' },
  { id: 'sentences', name: 'Sentences' },
  { id: 'pos', name: 'POS' },
  { id: 'entities', name: 'Entities' },
];

export function NlpAnalysisDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [documentUuid, setDocumentUuid] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('text');
  const [includeBlocks, setIncludeBlocks] = useState<BlockType[]>(
    DEFAULT_INCLUDE_BLOCKS,
  );

  const documents = useNlpDocuments(open);
  const text = useNlpDocumentText(documentUuid);
  const analysis = useNlpAnalysis(documentUuid, includeBlocks);

  const toggleBlockType = (type: BlockType) => {
    setIncludeBlocks((current) => {
      const next =
        current.includes(type) ?
          current.filter((t) => t !== type)
        : [...current, type];
      // Keep the server's canonical order so the query key is stable.
      return SELECTABLE_BLOCK_TYPES.filter((t) => next.includes(t));
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="5xl"
    >
      <DialogTitle>NLP Analysis</DialogTitle>
      <DialogBody className="flex flex-col gap-4 max-h-[80vh]">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-72">
            <Select
              value={documentUuid ?? ''}
              onChange={(e) => setDocumentUuid(e.target.value || null)}
            >
              <option value="">Select a document…</option>
              {(documents.data ?? []).map((doc) => (
                <option
                  key={doc.document_uuid}
                  value={doc.document_uuid}
                >
                  {doc.project_name} — {doc.file_name} ({doc.number_of_pages} p)
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-wrap gap-3">
            {SELECTABLE_BLOCK_TYPES.map((type) => (
              <CheckboxField key={type}>
                <Checkbox
                  checked={includeBlocks.includes(type)}
                  onChange={() => toggleBlockType(type)}
                />
                <Label className="text-xs">{BLOCK_TYPE_LABELS[type]}</Label>
              </CheckboxField>
            ))}
          </div>
        </div>

        {documentUuid === null ?
          <div className="py-16 text-center text-sm text-zinc-500">
            Pick a Baubeschreibung to analyze.
          </div>
        : <>
            <nav className="flex gap-4 border-b border-zinc-200 dark:border-zinc-700">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`border-b-2 px-1 pb-2 text-sm font-medium transition ${
                    tab === t.id ?
                      'border-blue-600 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
                  }`}
                >
                  {t.name}
                </button>
              ))}
            </nav>

            <div className="min-h-64 max-h-[60vh] overflow-auto">
              {tab === 'text' &&
                (text.isPending ?
                  <LoadingState label="Reflowing document (first run infers the layout — up to ~1 min)…" />
                : text.isError ?
                  <div className="text-sm text-red-600">
                    Failed to load text.
                  </div>
                : <TextTab
                    text={text.data}
                    includeBlocks={includeBlocks}
                  />)}
              {tab === 'sentences' &&
                (analysis.isPending || text.isPending ?
                  <LoadingState label="Analyzing…" />
                : analysis.isError || text.isError ?
                  <div className="text-sm text-red-600">Analysis failed.</div>
                : <SentencesTab
                    analysis={analysis.data}
                    text={text.data}
                  />)}
              {tab === 'pos' &&
                (analysis.isPending ? <LoadingState label="Analyzing…" />
                : analysis.isError ?
                  <div className="text-sm text-red-600">Analysis failed.</div>
                : <PosTab analysis={analysis.data} />)}
              {tab === 'entities' &&
                (analysis.isPending ? <LoadingState label="Analyzing…" />
                : analysis.isError ?
                  <div className="text-sm text-red-600">Analysis failed.</div>
                : <EntitiesTab analysis={analysis.data} />)}
            </div>
          </>
        }
      </DialogBody>
    </Dialog>
  );
}
