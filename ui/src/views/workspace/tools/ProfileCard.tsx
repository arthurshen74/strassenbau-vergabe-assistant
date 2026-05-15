// Inline renderer for `view_profile` and `update_profile` tool results.
// Both return the same ProfileDTO shape, so a single component handles
// both. The data field on a successful function_call_output carries the
// DTO; we cast at the boundary because the tool-output data field is
// typed as a free record.

import type { ProfileDTO } from '../../../types/generated';
import { Heading } from '../../../components/ui/heading';
import { Text } from '../../../components/ui/text';
import { Badge } from '../../../components/ui/badge';

interface ProfileCardProps {
  data: ProfileDTO;
  /** Hint for the section header — “Profile” for view, “Profile updated” for update. */
  variant?: 'view' | 'update';
}

export function ProfileCard({ data, variant = 'view' }: ProfileCardProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Heading level={4}>{variant === 'update' ? 'Profile updated' : 'Profile'}</Heading>
        <Badge color="zinc">{data.years_experience} yrs</Badge>
      </div>
      <div className="flex flex-col gap-1">
        <Text className="font-medium text-zinc-900 dark:text-zinc-100">{data.name}</Text>
        {data.resume_text && (
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
              Resume
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
              {data.resume_text}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
