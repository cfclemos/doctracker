# Examples

Small projects, one per case, to see how doctracker reads a repository. Each one can be opened on
its own:

```bash
cd examples/<case>
doctracker start
```

| Case | What it shows |
| --- | --- |
| `src-layout` | a package in `src/`, with tests next to it |
| `flat-layout` | a package right at the project root, no `src/` |
| `monorepo` | members in `packages/`: two in Python sharing the namespace package `acme` (with JS, CSS and HTML), and one each in Java, C#, C, Go, Rust, TypeScript, PHP and SQL |
| `frontend-only` | HTML, CSS and JavaScript, no Python |
| `skipped` | folders doctracker never reads (`venv`, `node_modules`) next to a file it reads |

The Java, C#, C, Go, Rust, TypeScript, PHP and SQL members wait for those languages to be read.

They are not part of doctracker's package: the build takes only `src/doctracker`.
