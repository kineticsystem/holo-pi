# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pull Request Notes

Each pull request has a notes file in [docs/pr/](../docs/pr/README.md): what we discussed, what we chose, and why. One file per pull request, written while the branch is open. Keep them simple: short sentences, one idea per paragraph, and a Mermaid diagram when it explains faster than words.

## Diagrams

The diagrams of the documents follow the `beautiful-mermaid-diagrams` skill, not the blue style of `write-docs`: colours by role, compact, readable in light and dark mode. Each is shown as an image: its source is `docs/diagrams/<name>.mmd`, rendered by `bin/render-diagrams.sh` into an SVG beside it (it needs Node.js and Google Chrome or Chromium); commit both. `bin/check-diagrams.sh` fails when an SVG is older than its source. British spelling (centre, colour).

## The API

The HTTP API is REST, on `/api`: resources named by plural nouns, `/api/media`, or by a singleton, `/api/display`, with GET, POST, PUT and DELETE, not verbs in the paths. A creation answers `201` with its `Location`, a removal `204`, and every error `{"error": "..."}`.

Swagger UI documents it, on `/api/docs`, from the code: every route has `tags`, a `summary`, a docstring and its error answers in `responses`, and every field of its models a `description` and an example. `test_documents_every_route` checks the routes. A change to the API goes into [docs/API.md](../docs/API.md) and the README's tables in the same change, and into `HoloPiApi` of `web/` if the page uses it.

## The Web Page

`web/` follows the `react-developer` skill: one store, services injected through providers from `App`, rules in hooks with their tests, components that know only their props. `pnpm typecheck`, `pnpm test` and `pnpm build` pass before a change is done.

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs the Python tests in Debian 13, the web page's checks and the image's build. Keep a new test, package or build step in it.
