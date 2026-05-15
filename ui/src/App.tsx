import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ConversationRouter } from './views/ConversationRouter';
import { NewThreadView } from './views/NewThreadView';
import { HomeRedirect } from './views/HomeRedirect';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomeRedirect />} />
          {/* /c/new must come before /c/:id so it doesn't get matched as an id. */}
          <Route path="/c/new" element={<NewThreadView />} />
          <Route path="/c/:conversationId" element={<ConversationRouter />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
