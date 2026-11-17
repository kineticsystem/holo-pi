import { cpSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

// The development server, with hot reload, on port 5177, next to stepit-macro's 5173 to 5176. It sends /api to
// HoloPi's server: the Raspberry Pi's by default, another with HOLO_PI_URL, e.g. http://localhost:8095.
const HOLO_PI_URL = process.env.HOLO_PI_URL ?? 'http://holo.local:8095';

// The files of Swagger UI, copied into dist/swagger-ui by the build: the server shows the API's documentation with
// them, on /api/docs, also on a network without the internet.
const SWAGGER_FILES = ['swagger-ui-bundle.js', 'swagger-ui.css', 'favicon-32x32.png'];

function swaggerUi(): Plugin {
  return {
    name: 'swagger-ui',
    apply: 'build',
    closeBundle() {
      const source = dirname(createRequire(import.meta.url).resolve('swagger-ui-dist/package.json'));
      const target = join('dist', 'swagger-ui');
      mkdirSync(target, { recursive: true });
      for (const file of SWAGGER_FILES) {
        cpSync(join(source, file), join(target, file));
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), swaggerUi()],
  server: { host: '0.0.0.0', port: 5177, strictPort: true, proxy: { '/api': HOLO_PI_URL } },
  build: { outDir: 'dist', emptyOutDir: true },
});
