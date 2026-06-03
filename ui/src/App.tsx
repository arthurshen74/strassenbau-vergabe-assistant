import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ConversationRouter } from './views/ConversationRouter';
import { Home } from './views/Home';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />
          <Route path="/c/:conversationId" element={<ConversationRouter />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
