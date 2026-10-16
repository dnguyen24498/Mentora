import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Component tests (V0-007 UI component tests). Dev-only tooling: no production
// dependency is added, and the production build (`npm run build`, which runs
// `tsc --noEmit && vite build`) is unchanged.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
