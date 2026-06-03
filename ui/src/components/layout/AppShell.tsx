// The application shell: persistent sidebar on the left, and the routed content on the right.
// A sidebar command or single-shot dispatch opens the global main window, which overlays the
// routed content until closed — so commands work whether or not a conversation is open.

import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { MainWindow } from '../mainwindow/MainWindow';
import { useMainWindowStore } from '../../store/mainWindow';

export function AppShell() {
  const mainView = useMainWindowStore((s) => s.view);
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        {mainView ? <MainWindow view={mainView} /> : <Outlet />}
      </main>
    </div>
  );
}
