import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
      'next/link': fileURLToPath(
        new URL('./node_modules/vinext/dist/shims/link.js', import.meta.url),
      ),
    },
  },
  test: { environment: 'jsdom', setupFiles: ['./vitest.setup.ts'] },
});
