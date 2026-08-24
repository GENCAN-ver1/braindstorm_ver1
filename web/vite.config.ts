import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => {
  const useMock = mode === 'test' || mode === 'mock'
  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@brainstorm-api-adapter': fileURLToPath(
          new URL(useMock ? './src/api/developmentMock.ts' : './src/api/httpApi.ts', import.meta.url),
        ),
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
