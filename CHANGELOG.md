# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-05

Initial public release.

### Added

- A JSON spec format for plain state machines (title, initial state, states,
  transitions), with a machine-readable schema in
  `walkforge/spec_schema.json`. Limits: 50 states and 200 transitions.
- `walkforge init` writes a six-state example spec that already validates and
  never overwrites an existing file.
- `walkforge validate` reports structural problems with an `S:` prefix and the
  JSON path, and graph problems as rules E1-E8 (errors) and W1 (unreachable
  state, warning).
- `walkforge render` writes one self-contained HTML page: a graph with a
  "you are here" marker next to the current state's description and choice
  buttons, with keyboard choices, history chips, back, restart, an end banner,
  a mobile layout and light and dark themes. Every asset is inlined, and the
  page's Content-Security-Policy blocks all network requests.
- Optional LLM drafting: `walkforge new "<situation>"` and
  `walkforge revise "<instruction>" <spec>` call the Anthropic API when
  `ANTHROPIC_API_KEY` is set and the `llm` extra is installed. Output is
  validated with one repair attempt; `revise` writes `<name>.revised.json`
  unless `--in-place` is given, which keeps a numbered `.bak` copy. `--model`
  or `WALKFORGE_MODEL` overrides the default model. This path is covered by
  mocked contract tests only and has not been run against the live API.
- Exit codes `0` (success), `1` (validation or write failure) and `2` (usage
  error).
- An example Claude Code skill for writing specs in
  `examples/claude-skill/walkthrough`.
- No runtime dependencies beyond the standard library, Python 3.9+.
