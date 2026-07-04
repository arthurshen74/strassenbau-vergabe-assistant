import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { Home } from './views/Home';
import { EvalView } from './views/eval/EvalView';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />
          {/* The route only carries the param; the conversation itself renders
              through AppShell's TabHost, which keeps every open tab mounted. */}
          <Route path="/c/:conversationId" element={null} />
          <Route path="/p/:projectUuid/eval" element={<EvalView />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
