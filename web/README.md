# HoloPi's Web Page

A page to try HoloPi without knowing its API: what the Looking Glass shows, the library of media kept on the Raspberry Pi, to show with a click on a row or the arrow keys, to download or remove, and uploads, one file or many, dropped on it or chosen. It uses the API only, as any client, and links its documentation, on `/api/docs`. The server serves it on `/`, e.g. http://holo.local:8095.

React, TypeScript and Vite, built with pnpm, as the web pages of the StepIt projects. How it is laid out, and why, is in [The Web Page](../docs/ARCHITECTURE.md#the-web-page) of the architecture document.

## Commands

From this folder, with Node.js 24 and pnpm, which `corepack enable` provides at the version `package.json` pins:

| Command | What it does |
|---|---|
| `pnpm install` | Installs the packages of `pnpm-lock.yaml`. |
| `pnpm dev` | Serves the page on http://localhost:5177, reloaded at each change, with the API of the Pi, http://holo.local:8095, or of the server `HOLO_PI_URL` names. |
| `pnpm test` | Runs the tests, with Vitest and Testing Library, against a fake API. |
| `pnpm typecheck` | Checks the types. |
| `pnpm build` | Checks the types and writes the page to `dist/`, with Swagger UI's files in `dist/swagger-ui`, for the server's documentation. |

For example, against a server on this computer:

```bash
HOLO_PI_URL=http://localhost:8095 pnpm dev
```

On the Pi, the image builds the page, so a change here needs `./docker/dock.sh build` there.
