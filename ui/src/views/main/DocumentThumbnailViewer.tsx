// Paged thumbnail viewer: one rendered page at a time, served by the thumbnail endpoint.

import { useState } from 'react';

import { apiBase } from '../../api/client';
import { Text } from '../../components/ui/text';
import { PageNav } from './PageNav';

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

  const url = `${apiBase}/projects/${projectUuid}/documents/${documentUuid}/pages/${page}/thumbnail`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-center">
        <img
          src={url}
          alt={`Page ${page}`}
          className="max-h-[55vh] rounded border border-zinc-950/10 dark:border-white/10"
        />
      </div>
      <Text className="text-center text-xs">
        Page {page} / {numberOfPages}
      </Text>
      <PageNav page={page} totalPages={numberOfPages} onChange={setPage} />
    </div>
  );
}
