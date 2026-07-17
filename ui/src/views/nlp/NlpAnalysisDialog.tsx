// NLP analysis modal. The source is fixed at open (nlpModal store): either an
// analyzable document (from the Documents tab) or ad-hoc text (an LV item's
// Langtext/Hinweis). There is no in-modal source selection. Tabs (Text, Sentences,
// POS, Entities) run over the active source; Entities and Sentences can flag
// mispredictions.

import { useEffect, useState } from "react";

import {
  useNlpAnalysis,
  useNlpDocumentText,
  useNlpTextAnalysis,
  type BlockType,
} from "../../api/nlp";
import { useNlpModalStore } from "../../store/nlpModal";
import type { AnalyzeResponse } from "../../types/generated";
import { Checkbox, CheckboxField } from "../../components/ui/checkbox";
import { Dialog, DialogBody, DialogTitle } from "../../components/ui/dialog";
import { Label } from "../../components/ui/fieldset";
import { LoadingState } from "../../components/feedback/LoadingState";
import {
  BLOCK_TYPE_LABELS,
  DEFAULT_INCLUDE_BLOCKS,
  SELECTABLE_BLOCK_TYPES,
} from "./blockTypes";
import { EntitiesTab } from "./EntitiesTab";
import { PosTab } from "./PosTab";
import { SentencesTab } from "./SentencesTab";
import { TextTab } from "./TextTab";
import type { FlagContext } from "./flagTypes";

type Tab = "text" | "sentences" | "pos" | "entities";

const TABS: { id: Tab; name: string }[] = [
  { id: "text", name: "Text" },
  { id: "sentences", name: "Sentences" },
  { id: "pos", name: "POS" },
  { id: "entities", name: "Entities" },
];

function flattenEntities(
  analysis: AnalyzeResponse,
): FlagContext["entitySnapshot"] {
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
  const source = useNlpModalStore((s) => s.source);
  const close = useNlpModalStore((s) => s.closeNlpAnalysis);

  const [tab, setTab] = useState<Tab>("text");
  const [includeBlocks, setIncludeBlocks] = useState<BlockType[]>(
    DEFAULT_INCLUDE_BLOCKS,
  );

  const isText = source?.kind === "text";

  // A document launch opens on Text; an LV text launch opens on Entities.
  useEffect(() => {
    if (!open || !source) return;
    setTab(source.kind === "text" ? "entities" : "text");
  }, [open, source]);

  const documentUuid = source?.kind === "document" ? source.documentUuid : null;
  const analyzedText = source?.kind === "text" ? source.text : null;

  const documentText = useNlpDocumentText(documentUuid);
  const documentAnalysis = useNlpAnalysis(documentUuid, includeBlocks);
  const textAnalysis = useNlpTextAnalysis(analyzedText, includeBlocks);

  const analysis = isText ? textAnalysis : documentAnalysis;

  const toggleBlockType = (type: BlockType) => {
    setIncludeBlocks((current) => {
      const next = current.includes(type)
        ? current.filter((t) => t !== type)
        : [...current, type];
      return SELECTABLE_BLOCK_TYPES.filter((t) => next.includes(t));
    });
  };

  const sourceText = isText
    ? (analyzedText ?? "")
    : (documentText.data?.blocks.map((b) => b.text).join("\n\n") ?? "");
  const flagContext: FlagContext = {
    sourceText,
    entitySnapshot: analysis.data ? flattenEntities(analysis.data) : [],
    lvItemUuid: source?.kind === "text" ? (source.lvItemUuid ?? null) : null,
    documentUuid:
      source?.kind === "text" ? (source.documentUuid ?? null) : documentUuid,
  };
  const labelOptions = analysis.data?.entities.labels.map((l) => l.label) ?? [];

  return (
    <Dialog open={open} onClose={close} size="5xl">
      <DialogTitle>NLP Analysis</DialogTitle>
      <DialogBody className="flex max-h-[80vh] flex-col gap-4">
        {source && (
          <div className="text-xs text-zinc-500">
            Source: {source.sourceLabel}
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

        <nav className="flex gap-4 border-b border-zinc-200 dark:border-zinc-700">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`border-b-2 px-1 pb-2 text-sm font-medium transition ${
                tab === t.id
                  ? "border-blue-600 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
              }`}
            >
              {t.name}
            </button>
          ))}
        </nav>

        <div className="max-h-[60vh] min-h-64 overflow-auto">
          {tab === "text" &&
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
          {tab === "sentences" &&
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
          {tab === "pos" &&
            (analysis.isPending ? (
              <LoadingState label="Analyzing…" />
            ) : analysis.isError ? (
              <div className="text-sm text-red-600">Analysis failed.</div>
            ) : (
              <PosTab analysis={analysis.data} />
            ))}
          {tab === "entities" &&
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
      </DialogBody>
    </Dialog>
  );
}
