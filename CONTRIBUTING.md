# Contributing to walkforge

Thanks for your interest! Bug reports, specs that render badly and pull
requests are welcome.

## Development setup

```sh
python -m venv .venv && source .venv/bin/activate
python -m pip install -e . pytest     # the `anthropic` extra is not needed
python -m pytest tests/ -q
walkforge --help
```

CI runs the suite on Python 3.9 and 3.12, without the `anthropic` SDK
installed; please keep both working.

## Guidelines

- **No runtime dependencies.** The base install is standard library only.
  `anthropic` stays an optional extra, imported only by `new` and `revise`,
  and the tests stub the client instead of installing it.
- **No network in tests.** A test must never call a real API.
- **The page stays self-contained.** Every asset is inlined and the
  Content-Security-Policy keeps `default-src 'none'`; do not add a CDN, font or
  remote request.
- **Escape spec text.** Spec strings are untrusted input to the page; keep
  hostile-text coverage in the renderer tests.
- **Spec changes go everywhere at once.** A change to the spec format updates
  `walkforge/spec_schema.json`, the validator and the README table together.
- Add a regression test for any bug fix.

## Pull requests

Keep PRs focused on one change, describe what changed and how you verified
it, and make sure `python -m pytest tests/ -q` is green before opening one.
