// LV-Texte tab body: the LV document's free text outside the positions, in document order.
// Vortext and Nachtext are the Zusätzlichen Texte (GAEB 90 T-lines, GAEB XML AddText);
// Hinweise are the Hinweistexte, each tagged with the LV-Gruppe it sits in ("LV" at the root).

import { Badge } from "../../components/ui/badge";
import { Subheading } from "../../components/ui/heading";
import { Text } from "../../components/ui/text";
import { LoadingState } from "../../components/feedback/LoadingState";
import { ErrorState } from "../../components/feedback/ErrorState";
import { useProjectLvTexts } from "../../api/projects";
import type { LVText } from "../../types/generated";

const ROOT_SCOPE_LABEL = "LV";

function scopeLabel(text: LVText): string {
  if (text.kind === "ADD_TEXT") {
    return text.placement === "after" ? "Nachtext" : "Vortext";
  }
  return text.parent_oz ?? ROOT_SCOPE_LABEL;
}

function TextBlock({ text }: { text: LVText }) {
  return (
    <article className="flex flex-col gap-1 rounded-md border border-zinc-950/10 p-3 dark:border-white/10">
      <div className="flex items-center gap-2">
        <Badge color={text.kind === "ADD_TEXT" ? "amber" : "zinc"}>
          {scopeLabel(text)}
        </Badge>
        {text.oz && <span className="text-xs text-zinc-500">OZ {text.oz}</span>}
        {text.heading && (
          <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {text.heading}
          </span>
        )}
      </div>
      {text.body && (
        <div className="max-h-96 overflow-y-auto text-sm whitespace-pre-wrap text-zinc-900 dark:text-zinc-100">
          {text.body}
        </div>
      )}
    </article>
  );
}

function Section({ title, texts }: { title: string; texts: LVText[] }) {
  if (texts.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <Subheading level={3}>
        {title} ({texts.length})
      </Subheading>
      {texts.map((t) => (
        <TextBlock key={t.lv_text_uuid} text={t} />
      ))}
    </section>
  );
}

export function LVTextsPanel({ projectUuid }: { projectUuid: string }) {
  const texts = useProjectLvTexts(projectUuid);

  if (texts.isPending) return <LoadingState label="Loading LV texts…" />;
  if (texts.isError) {
    return (
      <ErrorState
        message={(texts.error as Error).message}
        onRetry={() => texts.refetch()}
      />
    );
  }
  const all = texts.data;
  if (all.length === 0) {
    return <Text>This LV carries no Vorbemerkungen, Hinweise or Nachtext.</Text>;
  }
  const vortext = all.filter((t) => t.kind === "ADD_TEXT" && t.placement !== "after");
  const nachtext = all.filter((t) => t.kind === "ADD_TEXT" && t.placement === "after");
  const hinweise = all.filter((t) => t.kind === "REMARK");

  return (
    <div className="flex flex-col gap-6 overflow-y-auto">
      <Section title="Vortext" texts={vortext} />
      <Section title="Hinweise" texts={hinweise} />
      <Section title="Nachtext" texts={nachtext} />
    </div>
  );
}
