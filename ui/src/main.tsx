import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { APP_CONSTANTS } from './appconstants.ts';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: APP_CONSTANTS.MAX_RETRIES,
      staleTime: APP_CONSTANTS.STALE_TIMEOUT_MS,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
