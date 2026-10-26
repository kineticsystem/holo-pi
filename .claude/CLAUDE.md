# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Pull Request Notes

Each pull request has a notes file in [docs/pr/](../docs/pr/README.md): what we discussed, what we chose, and why. One file per pull request, written while the branch is open. Keep them simple: short sentences, one idea per paragraph, and a Mermaid diagram when it explains faster than words.

## Diagrams

The diagrams of the documents follow the `beautiful-mermaid-diagrams` skill, not the blue style of `write-docs`: colours by role, compact, readable in light and dark mode. Each is shown as an image: its source is `docs/diagrams/<name>.mmd`, rendered by `bin/render-diagrams.sh` into an SVG beside it (it needs Node.js and Google Chrome or Chromium); commit both. `bin/check-diagrams.sh` fails when an SVG is older than its source. British spelling (centre, colour).
