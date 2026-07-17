// Query hooks for the NLP analysis modal: reflowed text, sentence/POS analysis
// (parameterized by included block types), and displacy renders. Render results
// are cached client-side per sentence_hash+style via the query key; the server
// additionally caches dep SVGs by content hash.

import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AnalyzeResponse,
  DocumentTextRead,
  RenderResponse,
} from "../types/generated";

export type BlockType = DocumentTextRead["blocks"][number]["block_type"];
export type RenderStyle = "dep" | "ent";

export const nlpKeys = {
  all: ["nlp"] as const,
  text: (documentUuid: string) =>
    [...nlpKeys.all, "text", documentUuid] as const,
  analysis: (documentUuid: string, includeBlocks: BlockType[]) =>
    [...nlpKeys.all, "analysis", documentUuid, includeBlocks] as const,
  textAnalysis: (textHash: string, includeBlocks: BlockType[]) =>
    [...nlpKeys.all, "text-analysis", textHash, includeBlocks] as const,
  render: (sentenceHash: string, style: RenderStyle) =>
    [...nlpKeys.all, "render", sentenceHash, style] as const,
};

// Stable short key for an ad-hoc text (djb2), so the analysis query key doesn't
// carry the full text but still changes when the text does.
function hashText(text: string): string {
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(36);
}

// Reflow (and first-time layout inference) can take ~30s for an uncached
// document; keep the result fresh for the session, no refetch on focus.
export function useNlpDocumentText(documentUuid: string | null) {
  return useQuery({
    queryKey: nlpKeys.text(documentUuid ?? ""),
    queryFn: () =>
      api.get<DocumentTextRead>(`/nlp/documents/${documentUuid}/text`),
    enabled: documentUuid !== null,
    staleTime: Infinity,
  });
}

export function useNlpAnalysis(
  documentUuid: string | null,
  includeBlocks: BlockType[],
) {
  return useQuery({
    queryKey: nlpKeys.analysis(documentUuid ?? "", includeBlocks),
    queryFn: () =>
      api.post<AnalyzeResponse>("/nlp/analyze", {
        document_uuid: documentUuid,
        include_blocks: includeBlocks,
      }),
    enabled: documentUuid !== null,
    staleTime: Infinity,
  });
}

// Ad-hoc text analysis (LV Langtext/Hinweis, pasted text): same response shape,
// keyed by a hash of the text so distinct texts cache separately.
export function useNlpTextAnalysis(
  text: string | null,
  includeBlocks: BlockType[],
) {
  return useQuery({
    queryKey: nlpKeys.textAnalysis(text ? hashText(text) : "", includeBlocks),
    queryFn: () =>
      api.post<AnalyzeResponse>("/nlp/analyze", {
        text,
        include_blocks: includeBlocks,
      }),
    enabled: text !== null && text.trim() !== "",
    staleTime: Infinity,
  });
}

// Render on demand: the component flips `enabled` on first click; the query
// cache then holds the markup per sentence hash + style.
export function useNlpRender(
  sentenceHash: string,
  style: RenderStyle,
  text: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: nlpKeys.render(sentenceHash, style),
    queryFn: () => api.post<RenderResponse>("/nlp/render", { style, text }),
    enabled,
    staleTime: Infinity,
  });
}
