// Paged thumbnail viewer for a document: one rendered page at a time, served by the existing
// thumbnail endpoint. First / Back / Next / Last / GoToPage controls.

import { useState } from 'react';

import { apiBase } from '../../api/client';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Text } from '../../components/ui/text';

export function DocumentThumbnailViewer({
  projectUuid,
  documentUuid,
  numberOfPages,
}: {
  projectUuid: string;
  documentUuid: string;
  numberOfPages: number;
}) {
  const [page, setPage] = useState(1);

  if (numberOfPages <= 0) return <Text>This document has no rendered pages.</Text>;

  const clamp = (n: number) => Math.min(Math.max(n, 1), numberOfPages);
  const url = `${apiBase}/projects/${projectUuid}/documents/${documentUuid}/pages/${page}/thumbnail`;

  return (
    <div className="flex flex-col items-center gap-3">
      <img
        src={url}
        alt={`Page ${page}`}
        className="max-h-[55vh] rounded border border-zinc-950/10 dark:border-white/10"
      />
      <div className="flex items-center gap-2">
        <Button plain disabled={page <= 1} onClick={() => setPage(1)}>
          First
        </Button>
        <Button plain disabled={page <= 1} onClick={() => setPage(clamp(page - 1))}>
          Back
        </Button>
        <Text className="text-xs">
          Page {page} / {numberOfPages}
        </Text>
        <Button plain disabled={page >= numberOfPages} onClick={() => setPage(clamp(page + 1))}>
          Next
        </Button>
        <Button plain disabled={page >= numberOfPages} onClick={() => setPage(numberOfPages)}>
          Last
        </Button>
        <Input
          type="number"
          min={1}
          max={numberOfPages}
          aria-label="Go to page"
          className="w-20"
          onChange={(e) => {
            const n = Number(e.target.value);
            if (Number.isFinite(n) && n >= 1) setPage(clamp(n));
          }}
        />
      </div>
    </div>
  );
}
