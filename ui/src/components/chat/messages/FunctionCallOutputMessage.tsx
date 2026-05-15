// Wrapper that lets the parent (a view) supply the actual tool-result
// renderer. The Message component never knows which tool produced the
// output — it just delegates here, and here we delegate to the view.
//
// Failed outputs are filtered upstream in MessageList per FRONTEND.md §4
// ("Do NOT show failed tool calls in the UI").

import type { FunctionCallOutputMessageDTO } from '../../../types/generated';
import { InlineToolResult } from '../InlineToolResult';

interface Props {
  m: FunctionCallOutputMessageDTO;
  renderToolResult?: (msg: FunctionCallOutputMessageDTO) => React.ReactNode;
}

export function FunctionCallOutputMessage({ m, renderToolResult }: Props) {
  if (!m.success) return null;
  const content =
    renderToolResult ?
      renderToolResult(m)
    : <pre className="overflow-auto text-xs text-zinc-700 dark:text-zinc-300">
        {JSON.stringify(m.data, null, 2)}
      </pre>;
  // Individual tool renderers can opt out by returning null (e.g. when
  // navigation handles the UX and no inline card is needed).
  if (content == null) return null;
  return (
    <div className="flex justify-start w-full">
      <InlineToolResult>{content}</InlineToolResult>
    </div>
  );
}
