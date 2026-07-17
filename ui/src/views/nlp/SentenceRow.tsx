// One sentence with dep/ent render buttons. Markup is fetched on first click
// (query stays cached per sentence hash + style) and injected inline; dep SVGs
// keep a white background because displacy hardcodes dark-on-light colors.

import { useRef, useState } from 'react';

import { useNlpRender, type RenderStyle } from '../../api/nlp';
import type { SentenceInfo } from '../../types/generated';
import type { FlagTarget } from './flagTypes';

function RenderPane({
  sentence,
  style,
}: {
  sentence: SentenceInfo;
  style: RenderStyle;
}) {
  const render = useNlpRender(
    sentence.sentence_hash,
    style,
    sentence.text,
    true,
  );

  if (render.isPending) {
    return <div className="py-2 text-xs text-zinc-500">Rendering {style}…</div>;
  }
  if (render.isError) {
    return <div className="py-2 text-xs text-red-600">Render failed.</div>;
  }
  // An ent render without <mark> means the model found no entities — say so,
  // otherwise it reads as a broken render.
  if (style === 'ent' && !render.data.markup.includes('<mark')) {
    return (
      <div className="py-2 text-xs text-zinc-500">
        No entities found (de_core_news_lg only knows PER/LOC/ORG/MISC).
      </div>
    );
  }
  return (
    <div
      className={`overflow-x-auto rounded-md border border-zinc-200 p-2 dark:border-zinc-700 ${
        style === 'dep' ? 'bg-white' : 'bg-white'
      }`}
      dangerouslySetInnerHTML={{ __html: render.data.markup }}
    />
  );
}

export function SentenceRow({
  sentence,
  onFlagMissed,
}: {
  sentence: SentenceInfo;
  onFlagMissed?: (target: FlagTarget) => void;
}) {
  const [open, setOpen] = useState<RenderStyle | null>(null);
  const [selection, setSelection] = useState<{ text: string; start: number } | null>(
    null,
  );
  const textRef = useRef<HTMLSpanElement>(null);

  // Capture a within-sentence text selection; reject selections that reach outside
  // this row (cross-sentence), so a miss flag always maps to one sentence.
  const onMouseUp = () => {
    if (!onFlagMissed) return;
    const sel = window.getSelection();
    const span = textRef.current;
    if (!sel || sel.isCollapsed || !span) {
      setSelection(null);
      return;
    }
    if (!span.contains(sel.anchorNode) || !span.contains(sel.focusNode)) {
      setSelection(null);
      return;
    }
    const selected = sel.toString().trim();
    const start = sentence.text.indexOf(selected);
    if (selected === '' || start < 0) {
      setSelection(null);
      return;
    }
    setSelection({ text: selected, start });
  };

  const submitMiss = () => {
    if (!onFlagMissed || !selection) return;
    onFlagMissed({
      spanText: selection.text,
      spanStart: selection.start,
      spanEnd: selection.start + selection.text.length,
      sentenceText: sentence.text,
      label: '',
      allowedKinds: ['missed_entity'],
    });
    setSelection(null);
  };

  const button = (style: RenderStyle, label: string) => (
    <button
      type="button"
      onClick={() => setOpen(open === style ? null : style)}
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition ${
        open === style ?
          'bg-blue-600 text-white'
        : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="border-b border-zinc-100 py-1.5 dark:border-zinc-800">
      <div className="flex items-start gap-2">
        <div className="flex shrink-0 gap-1 pt-0.5">
          {button('dep', 'dep')}
          {button('ent', 'ent')}
        </div>
        <span
          ref={textRef}
          onMouseUp={onMouseUp}
          className="text-sm text-zinc-800 dark:text-zinc-200"
        >
          {sentence.text}
        </span>
      </div>
      {selection && onFlagMissed && (
        <div className="mt-1 flex items-center gap-2 pl-12">
          <span className="text-[11px] text-zinc-500">
            “{selection.text}”
          </span>
          <button
            type="button"
            onClick={submitMiss}
            className="rounded bg-blue-600 px-1.5 py-0.5 text-[10px] font-medium text-white transition hover:bg-blue-700"
          >
            Flag as missed entity
          </button>
        </div>
      )}
      {open !== null && (
        <div className="mt-2">
          <RenderPane
            sentence={sentence}
            style={open}
          />
        </div>
      )}
    </div>
  );
}
