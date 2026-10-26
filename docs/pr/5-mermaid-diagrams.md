# Diagrams as SVG Images, from Mermaid Sources

Pull request [#5](https://github.com/kineticsystem/holo-pi/pull/5), branch `mermaid-diagrams`.

## Goal

Every diagram of the documents in one style, the one of the `beautiful-mermaid-diagrams` skill: colours by role, compact, readable in light and dark mode, as StepIt Macro and its modules did ([stepit-macro#103](https://github.com/kineticsystem/stepit-macro/pull/103)). There are two: the overview of the README and the parts of `docs/ARCHITECTURE.md`.

## Decisions

**An SVG image, not a Mermaid block.** GitHub stretches a Mermaid block to the width of the page, so a narrow diagram becomes very tall. An image shows at the width we give it. The source stays beside it, in `docs/diagrams/<name>.mmd`.

**A hash, not a render, to check it.** `bin/render-diagrams.sh` writes the SHA-256 of the source into the first line of the SVG. `bin/check-diagrams.sh` compares the two, without Node.js or Chrome. Whoever changes a `.mmd` renders it and commits both.

**Zone titles padded aside.** An arrow enters each zone at its centre, where Mermaid puts the title. Trailing `&nbsp;` move the title to the left, as in StepIt Camera.

**Roles by colour.** The interleaving is the hero node; the inputs, the entry points, the screens and the stores each have a colour. The quilt and the hologram are the thick arrows, the calibration the normal ones, the cache dotted.

## Left Out

A CI check. HoloPi has no CI: `bin/check-diagrams.sh` runs by hand, and the README says when.
