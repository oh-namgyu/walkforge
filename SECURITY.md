# Security

## Reporting a problem

Please open an issue at
<https://github.com/oh-namgyu/walkforge/issues>. There is no private
disclosure channel; if a finding should not be public, say so in a short
issue without the details and a maintainer will follow up.

## What walkforge does with your data

- **No secrets are stored.** walkforge reads `ANTHROPIC_API_KEY` from the
  environment when you run `new` or `revise`, hands it to the Anthropic SDK,
  and never writes it to disk or into any generated file.
- **Only `new` and `revise` use the network.** `init`, `validate` and
  `render` are offline and need nothing beyond the Python standard library.
  On `new` and `revise`, your situation or instruction text and the current
  spec are sent to the Anthropic API. Input is capped at 8,000 characters.
- **`--debug` writes your prompt to disk.** The transcript file is created
  with mode `0600` and never overwrites an existing file, and walkforge
  prints a reminder to delete it. Nothing is saved without the flag.
- **The rendered page is self-contained.** All CSS, JavaScript and graph
  markup are inlined, and the page carries
  `Content-Security-Policy: default-src 'none'` so it cannot load or contact
  anything. Opening a rendered walkthrough makes zero network requests.

## Handling untrusted specs

Spec text is escaped before it reaches the page: control characters and
invisible formatting characters are stripped, HTML metacharacters are
escaped, and the embedded JSON is written with every angle bracket escaped so
it cannot close its own `<script>` element. Rendering a spec you did not
write is nevertheless a judgement call — the text still becomes the page's
visible content.
