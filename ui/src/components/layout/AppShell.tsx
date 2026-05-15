// The application shell: persistent sidebar on the left, a single
// conversation pane on the right whose contents are routed.
// The prompt-execution-log drawer is mounted here so it persists across
// route changes and renders outside the sidebar scroll context.

import { Outlet } from 'react-router-dom';
import { PromptLogDrawer } from '../devtools/PromptLogDrawer';
import { useUIStore } from '../../store/ui';
import { Sidebar } from './Sidebar';

export function AppShell() {
  const promptLogDrawerOpen = useUIStore((s) => s.promptLogDrawerOpen);
  const closePromptLogDrawer = useUIStore((s) => s.closePromptLogDrawer);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </main>

      {/* Prompt execution log drawer — overlays the entire shell */}
      <PromptLogDrawer
        open={promptLogDrawerOpen}
        onClose={closePromptLogDrawer}
      />
    </div>
  );
}
