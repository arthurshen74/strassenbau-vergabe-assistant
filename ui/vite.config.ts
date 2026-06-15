import type { ClientRequest } from 'node:http';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// In docker-compose the API is reachable as `api:8000`; on the host it's
// `localhost:8000`. VITE_API_PROXY_TARGET (set in docker-compose.yml)
// flips the target without forking the config.
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // inotify events don't cross the Docker volume mount on macOS, so HMR would miss edits; poll.
    watch: { usePolling: true },
    proxy: {
      // The frontend calls `/api/*`, but the backend serves routes at the
      // root (`/conversations`, `/prompts`). Strip the `/api` prefix so the
      // proxied request matches a real backend path.
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // Force identity encoding upstream: gzip/br negotiation buffers SSE responses, which stalls
        // the calculator's live stream ("Thinking" with no messages until the segment ends).
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq: ClientRequest) => {
            proxyReq.setHeader('Accept-Encoding', 'identity');
          });
        },
      },
    },
  },
});
