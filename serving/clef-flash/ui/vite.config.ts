import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'CLEF_');
  return {
    base: './',
    plugins: [react()],
    server: {
      proxy: {
        '/v1/systemone': {
          target: env.CLEF_DEV_UPSTREAM || 'http://127.0.0.1:18080',
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  };
});
