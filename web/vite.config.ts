import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],
  build: {
    target: 'es2022',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          webllm: ['@mlc-ai/web-llm'],
          three: ['three'],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: false,
  },
});
