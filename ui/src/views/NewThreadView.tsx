// Lands when the user clicks "New thread" but before any text is sent.
// Creates a workspace conversation server-side and redirects to it.
//
// Implementation note: we call the API directly (not via useMutation) and
// navigate inside the Promise `.then()` callback. Promise callbacks always
// fire regardless of React component lifecycle, which makes this approach
// immune to React 18 StrictMode's double-mount behaviour.
//
// The StrictMode sequence is:
//   1. Mount  → startedRef set, API call begins (promise P)
//   2. Unmount (StrictMode teardown)
//   3. Remount → startedRef still true, no second call
//   4. P resolves → .then fires → invalidate sidebar + navigate
//
// Using useMutation instead would break step 4: TanStack Query v5 resets
// per-component mutation state on remount, so `create.isSuccess` is never
// seen as `true` on the remounted instance, leaving the view stuck.

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { conversationKeys } from '../api/conversations';
import type { ConversationDTO } from '../types/generated';
import { LoadingState } from '../components/feedback/LoadingState';
import { ErrorState } from '../components/feedback/ErrorState';

export function NewThreadView() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const startedRef = useRef(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    api
      .post<ConversationDTO>('/conversations', {})
      .then((data) => {
        qc.invalidateQueries({ queryKey: conversationKeys.all });
        navigate(`/c/${data.id}`, { replace: true });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err : new Error(String(err)));
      });
    // navigate and qc are stable references; listing them satisfies the
    // linter without causing the effect to re-run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <ErrorState
        message={error.message}
        onRetry={() => {
          startedRef.current = false;
          setError(null);
        }}
      />
    );
  }

  return <LoadingState label="Starting a new thread…" />;
}
