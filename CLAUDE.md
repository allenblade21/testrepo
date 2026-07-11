# CLAUDE.md

This file provides guidance to AI assistants (e.g. Claude Code) when working with code in this repository.

## Repository status

**This repository is currently empty** — it has no source code, build files, or
commit history yet. This document therefore describes the conventions in effect
rather than an existing codebase, and should be **updated as soon as real code
lands** so that it reflects the actual structure, tooling, and workflows.

- **Repository:** `allenblade21/testrepo`
- **Primary remote:** `origin` → `https://github.com/allenblade21/testrepo`

When code is added, replace the placeholder sections below with concrete
details: the tech stack, the directory layout, how to install dependencies, how
to build, how to run the test suite, and any project-specific conventions.

## Codebase structure

_No source files exist yet._ Once the project is scaffolded, document the
top-level layout here, for example:

```
.
├── src/            # application/library source
├── tests/          # test suite
├── docs/           # documentation
└── <build config>  # package manifest / build tooling
```

## Development workflows

_No build system or tooling is configured yet._ When it is, record the exact
commands here so they can be run without guessing. Typical entries to fill in:

- **Install dependencies:** _TBD_
- **Build:** _TBD_
- **Run the app:** _TBD_
- **Run tests:** _TBD_ (and how to run a single test)
- **Lint / format:** _TBD_
- **Type-check:** _TBD_

## Key conventions

_Add project-specific conventions here as they are established_ — code style,
naming, error handling, module boundaries, commit message format, and anything
non-obvious that an assistant should follow to match the surrounding code.

## Git & branching

- Do all development on a feature branch; do not commit directly to the default
  branch.
- Use descriptive, imperative commit messages.
- Push with `git push -u origin <branch-name>`.
- Do not open a pull request unless explicitly asked. When a PR is requested,
  check for a template under `.github/` and follow its structure.

---

_Last reviewed: 2026-07-11. This file was generated while the repository was
empty — update it to describe the real codebase once code is added._
