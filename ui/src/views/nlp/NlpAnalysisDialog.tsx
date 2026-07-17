// NLP analysis modal. Text source is either an analyzable document (picker) or
// ad-hoc text — free text pasted here, or an LV item's Langtext/Hinweis preloaded
// via the nlpModal store. Tabs (Text, Sentences, POS, Entities) run over whichever
// source is active; the Entities and Sentences tabs can flag mispredictions.

import { useEffect, useState } from 'react';

import {
  useNlpAnalysis,
  useNlpDocuments,
  useNlpDocumentText,
  useNlpTextAnalysis,
  type BlockType,
} from '../../api/nlp';
import { useNlpModalStore } from '../../store/nlpModal';
import type { AnalyzeResponse } from '../../types/generated';
import { Button } from '../../components/ui/button';
import { Checkbox, CheckboxField } from '../../components/ui/checkbox';
import { Dialog, DialogBody, DialogTitle } from '../../components/ui/dialog';
import { Label } from '../../components/ui/fieldset';
import { Select } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
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
import type { FlagContext } from './flagTypes';

type Tab = 'text' | 'sentences' | 'pos' | 'entities';
type SourceMode = 'document' | 'text';

const TABS: { id: Tab; name: string }[] = [
  { id: 'text', name: 'Text' },
  { id: 'sentences', name: 'Sentences' },
  { id: 'pos', name: 'POS' },
  { id: 'entities', name: 'Entities' },
];

function flattenEntities(analysis: AnalyzeResponse): FlagContext['entitySnapshot'] {
  return analysis.entities.labels.flatMap((label) =>
    label.occurrences.map((occ) => ({
      text: occ.text,
      label: label.label,
      pattern_id: occ.pattern_id ?? null,
    })),
  );
}

export function NlpAnalysisDialog() {
  const open = useNlpModalStore((s) => s.open);
  const preset = useNlpModalStore((s) => s.preset);
  const close = useNlpModalStore((s) => s.closeNlpAnalysis);

  const [sourceMode, setSourceMode] = useState<SourceMode>('document');
  const [documentUuid, setDocumentUuid] = useState<string | null>(null);
  const [textDraft, setTextDraft] = useState('');
  const [analyzedText, setAnalyzedText] = useState('');
  const [tab, setTab] = useState<Tab>('text');
  const [includeBlocks, setIncludeBlocks] = useState<BlockType[]>(
    DEFAULT_INCLUDE_BLOCKS,
  );

  // Initialize from the preset each time the modal opens.
  useEffect(() => {
    if (!open) return;
    if (preset) {
      setSourceMode('text');
      setTextDraft(preset.text);
      setAnalyzedText(preset.text);
      setTab('entities');
    } else {
      setSourceMode('document');
      setDocumentUuid(null);
      setTextDraft('');
      setAnalyzedText('');
      setTab('text');
    }
  }, [open, preset]);

  const isText = sourceMode === 'text';

  const documents = useNlpDocuments(open && !isText);
  const documentText = useNlpDocumentText(isText ? null : documentUuid);
  const documentAnalysis = useNlpAnalysis(isText ? null : documentUuid, includeBlocks);
  const textAnalysis = useNlpTextAnalysis(isText ? analyzedText : null, includeBlocks);

  const analysis = isText ? textAnalysis : documentAnalysis;
  const hasSource = isText ? analyzedText.trim() !== '' : documentUuid !== null;

  const toggleBlockType = (type: BlockType) => {
    setIncludeBlocks((current) => {
      const next =
        current.includes(type)
          ? current.filter((t) => t !== type)
          : [...current, type];
      return SELECTABLE_BLOCK_TYPES.filter((t) => next.includes(t));
    });
  };

  const sourceText = isText
    ? analyzedText
    : (documentText.data?.blocks.map((b) => b.text).join('\n\n') ?? '');
  const flagContext: FlagContext = {
    sourceText,
    entitySnapshot: analysis.data ? flattenEntities(analysis.data) : [],
    lvItemUuid: preset?.lvItemUuid ?? null,
    documentUuid: isText ? (preset?.documentUuid ?? null) : documentUuid,
  };
  const labelOptions = analysis.data?.entities.labels.map((l) => l.label) ?? [];

  return (
    <Dialog open={open} onClose={close} size="5xl">
      <DialogTitle>NLP Analysis</DialogTitle>
      <DialogBody className="flex max-h-[80vh] flex-col gap-4">
        <div className="flex gap-2">
          <SourceButton
            active={!isText}
            label="Document"
            onClick={() => setSourceMode('document')}
          />
          <SourceButton
            active={isText}
            label="Free text"
            onClick={() => setSourceMode('text')}
          />
          {preset && isText && (
            <span className="self-center text-xs text-zinc-500">
              Source: {preset.sourceLabel}
            </span>
          )}
        </div>

        {isText ? (
          <div className="flex flex-col gap-2">
            <Textarea
              rows={4}
              value={textDraft}
              onChange={(e) => setTextDraft(e.target.value)}
              placeholder="Paste text to analyze (e.g. an LV Langtext)…"
            />
            <div>
              <Button
                onClick={() => setAnalyzedText(textDraft)}
                disabled={textDraft.trim() === '' || textDraft === analyzedText}
              >
                Analyze
              </Button>
            </div>
          </div>
        ) : (
          <div className="min-w-72">
            <Select
              value={documentUuid ?? ''}
              onChange={(e) => setDocumentUuid(e.target.value || null)}
            >
              <option value="">Select a document…</option>
              {(documents.data ?? []).map((doc) => (
                <option key={doc.document_uuid} value={doc.document_uuid}>
                  {doc.project_name} — {doc.file_name} ({doc.number_of_pages} p)
                </option>
              ))}
            </Select>
          </div>
        )}

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

        {!hasSource ? (
          <div className="py-16 text-center text-sm text-zinc-500">
            {isText ? 'Paste text and press Analyze.' : 'Pick a Baubeschreibung to analyze.'}
          </div>
        ) : (
          <>
            <nav className="flex gap-4 border-b border-zinc-200 dark:border-zinc-700">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={`border-b-2 px-1 pb-2 text-sm font-medium transition ${
                    tab === t.id
                      ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
                  }`}
                >
                  {t.name}
                </button>
              ))}
            </nav>

            <div className="max-h-[60vh] min-h-64 overflow-auto">
              {tab === 'text' &&
                (isText ? (
                  <pre className="whitespace-pre-wrap text-sm text-zinc-800 dark:text-zinc-200">
                    {analyzedText}
                  </pre>
                ) : documentText.isPending ? (
                  <LoadingState label="Reflowing document (first run infers the layout — up to ~1 min)…" />
                ) : documentText.isError ? (
                  <div className="text-sm text-red-600">Failed to load text.</div>
                ) : (
                  <TextTab text={documentText.data} includeBlocks={includeBlocks} />
                ))}
              {tab === 'sentences' &&
                (analysis.isPending ? (
                  <LoadingState label="Analyzing…" />
                ) : analysis.isError ? (
                  <div className="text-sm text-red-600">Analysis failed.</div>
                ) : (
                  <SentencesTab
                    analysis={analysis.data}
                    text={isText ? null : (documentText.data ?? null)}
                    context={flagContext}
                    labelOptions={labelOptions}
                  />
                ))}
              {tab === 'pos' &&
                (analysis.isPending ? (
                  <LoadingState label="Analyzing…" />
                ) : analysis.isError ? (
                  <div className="text-sm text-red-600">Analysis failed.</div>
                ) : (
                  <PosTab analysis={analysis.data} />
                ))}
              {tab === 'entities' &&
                (analysis.isPending ? (
                  <LoadingState label="Analyzing…" />
                ) : analysis.isError ? (
                  <div className="text-sm text-red-600">Analysis failed.</div>
                ) : (
                  <EntitiesTab
                    analysis={analysis.data}
                    context={flagContext}
                    labelOptions={labelOptions}
                  />
                ))}
            </div>
          </>
        )}
      </DialogBody>
    </Dialog>
  );
}

function SourceButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-3 py-1.5 text-sm transition ${
        active
          ? 'border-blue-600 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
          : 'border-zinc-200 text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800'
      }`}
    >
      {label}
    </button>
  );
}
