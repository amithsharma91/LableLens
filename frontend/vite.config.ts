import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Port 3000 is deliberate and matches backend/.env.example ALLOWED_ORIGINS,
// so the frontend needs no backend CORS change. strictPort makes a port clash
// fail loudly instead of silently moving to a different origin (which would
// break the Supabase redirect allowlist and CORS both).
export default defineConfig({
  plugins: [react()],
  server: { port: 3000, strictPort: true, host: true },
  preview: { port: 3000, strictPort: true, host: true },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    // Threads share memory with the main process, unlike fork workers.
    // maxWorkers is 1 deliberately: this suite is small (a handful of
    // files) and a worker that cannot start is reported as a suite-level
    // ERROR, not a test failure, which is a confusing way to fail. Raise it
    // on machines with headroom if you want more parallelism.
    pool: 'threads',
    maxWorkers: 1,
    testTimeout: 20000,
    hookTimeout: 20000,
  },
});