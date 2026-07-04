// The application shell: persistent sidebar on the left; on the right the tab
// strip, then a panel stack (TabHost keeps every open conversation mounted).
// The main window and non-conversation routes render in an opaque overlay
// layer above the stack, so opening a command view or going Home never
// unmounts a conversation — its stream, form edits, and scroll survive.

import { Outlet, useParams } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TabStrip } from './TabStrip';
import { TabHost } from './TabHost';
import { MainWindow } from '../mainwindow/MainWindow';
import { useMainWindowStore } from '../../store/mainWindow';

export function AppShell() {
  const mainView = useMainWindowStore((s) => s.view);
  const { conversationId } = useParams();
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col max-h-screen">
        <TabStrip />
        <div className="relative min-h-0 flex-1">
          <TabHost />
          {(mainView || !conversationId) && (
            <div className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-zinc-950 overflow-y-auto">
              {mainView ?
                <MainWindow view={mainView} />
              : <Outlet />}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
