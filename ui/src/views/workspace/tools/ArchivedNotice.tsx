// Inline confirmation for `archive_position`. The tool returns the full
// PositionDTO; we just need to acknowledge the archive — the full card
// would imply the user might still act on it.

import type { PositionDTO } from '../../../types/generated';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';
import { ArchiveBoxIcon } from '@heroicons/react/16/solid';

function currentTitle(p: PositionDTO): string {
  const cv =
    p.versions.find((v) => v.version === p.current_version) ??
    p.versions[p.versions.length - 1];
  return `${cv.title} · ${cv.company}`;
}

export function ArchivedNotice({ data }: { data: PositionDTO }) {
  return (
    <div className="flex items-center gap-2">
      <ArchiveBoxIcon className="h-4 w-4 text-zinc-500" />
      <Text className="text-sm">Archived: {currentTitle(data)}</Text>
      <Badge color="zinc">archived</Badge>
    </div>
  );
}
