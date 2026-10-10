// Picks which LV document the LV Positions and LV-Texte tabs show: a listbox with several LV
// documents, the file name as a label with one, nothing with none.

import {
  Listbox,
  ListboxDescription,
  ListboxLabel,
  ListboxOption,
} from "../../components/ui/listbox";
import { formatRelativeTime } from "../../lib/format";
import type { DocumentRead } from "../../types/generated";

export function LvDocumentSelector({
  lvDocuments,
  selected,
  onChange,
}: {
  lvDocuments: DocumentRead[];
  selected: DocumentRead | undefined;
  onChange: (documentUuid: string) => void;
}) {
  if (!selected) return null;
  if (lvDocuments.length === 1) {
    return (
      <span className="text-xs text-zinc-500 dark:text-zinc-400">
        LV: {selected.file_name}
      </span>
    );
  }
  return (
    <div className="max-w-md">
      <Listbox
        value={selected.document_uuid}
        onChange={onChange}
        aria-label="LV document"
      >
        {lvDocuments.map((d) => (
          <ListboxOption key={d.document_uuid} value={d.document_uuid}>
            <ListboxLabel>{d.file_name}</ListboxLabel>
            <ListboxDescription>
              {formatRelativeTime(d.created_at)}
            </ListboxDescription>
          </ListboxOption>
        ))}
      </Listbox>
    </div>
  );
}
