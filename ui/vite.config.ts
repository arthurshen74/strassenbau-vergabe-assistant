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
    proxy: {
      '/api': apiTarget,
    },
  },
});
