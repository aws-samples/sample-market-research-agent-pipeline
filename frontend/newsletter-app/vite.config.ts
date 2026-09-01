import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: [
      '@aws-sdk/credential-provider-login',
      '@aws-sdk/credential-provider-process',
      '@aws-sdk/credential-provider-sso',
      '@aws-sdk/credential-provider-ini',
      '@aws-sdk/credential-provider-node',
    ],
  },
  build: {
    rollupOptions: {
      external: [
        /^node:/,
      ],
    },
  },
  define: {
    global: 'globalThis',
  },
  resolve: {
    alias: {
      './runtimeConfig': './runtimeConfig.browser',
      process: 'process/browser',
      stream: 'stream-browserify',
      util: 'util',
    },
  },
})
