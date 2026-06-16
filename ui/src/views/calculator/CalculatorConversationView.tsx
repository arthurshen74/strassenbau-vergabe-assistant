// Orchestrates the non-complete phases of an ekt_calculator conversation: a chat GATE while the run
// is still awaiting_start (the Kalkulator discusses the position or asks to run it), then the live
// RUN once it starts. Completed runs route to the normal workspace view (see ConversationRouter).

import { useState } from 'react';

import { useConversation } from '../../api/conversations';
import { LoadingState } from '../../components/feedback/LoadingState';
import { CalculatorGate } from './CalculatorGate';
import { CalculatorRun } from './CalculatorRun';

export function CalculatorConversationView({ conversationId }: { conversationId: string }) {
  const conversation = useConversation(conversationId);
  const projectUuid = conversation.data?.project_uuid ?? undefined;
  const status = conversation.data?.calculation_status;

  // Set when the gate hands off, so the run mounts and auto-starts even before the server status has
  // advanced past awaiting_start (the calc stream flips it to running once it opens).
  const [started, setStarted] = useState(false);
  const showGate = status === 'awaiting_start' && !started;

  if (conversation.isLoading) return <LoadingState />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center border-b border-zinc-950/5 px-4 dark:border-white/5">
        <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {conversation.data?.title ?? 'EKT calculation'}
        </div>
      </header>
      {showGate ? (
        <CalculatorGate
          conversationId={conversationId}
          projectUuid={projectUuid}
          onStart={() => setStarted(true)}
        />
      ) : (
        <CalculatorRun
          conversationId={conversationId}
          projectUuid={projectUuid}
          autoStart={started}
        />
      )}
    </div>
  );
}
