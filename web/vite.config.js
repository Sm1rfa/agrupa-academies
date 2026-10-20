import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In dev, /api is proxied to `php -S localhost:8000 -t ..` (project root).
// In production the built files sit next to the api/ folder, so base is relative.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: { outDir: '../dist', emptyOutDir: true },
});
