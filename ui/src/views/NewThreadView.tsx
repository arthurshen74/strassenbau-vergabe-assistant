// Lands when the user clicks "New thread" but before any text is sent.
// Creates a dispatcher conversation server-side and redirects to it.
//
// We call the API directly (not via useMutation) and navigate inside the
// Promise `.then()` so the flow is immune to React StrictMode's double-mount:
// the promise callback fires regardless of component lifecycle.

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { createAndSeedConversation } from '../api/conversations';
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

    createAndSeedConversation(qc)
      .then((created) => {
        navigate(`/c/${created.conversation_uuid}`, { replace: true });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err : new Error(String(err)));
      });
    // navigate and qc are stable references.
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
