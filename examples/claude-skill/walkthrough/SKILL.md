---
name: walkthrough
description: Turn a process, flow, or decision into a self-contained interactive HTML walkthrough with walkforge. Use when the user asks to "create a walkthrough", build a "state machine walkthrough", make an "explorable explanation" of a flow, or wants a runbook, onboarding guide, or decision tree someone can click through step by step rather than read as a static diagram.
---

# Building a walkthrough with walkforge

walkforge turns a small state-machine spec (JSON) into one self-contained HTML
page: a graph on the left, the current step and its choices on the right. No
build step, no network requests at runtime.

**Write the spec yourself.** That is the primary path inside Claude Code: you
already understand the flow being described, so drafting the JSON directly is
faster and more accurate than asking a model to invent it. `walkforge new
"<situation>"` exists for people working from a blank page, but it needs
`ANTHROPIC_API_KEY` and sends the situation text to the Anthropic API.

## 1. Write the spec

```json
{
  "title": "Production incident response",
  "description": "Optional one-line intro.",
  "initial": "page_received",
  "states": [
    {
      "id": "page_received",
      "name": "Page received",
      "description": "Where the reader is and what is happening, in two or three sentences.",
      "annotation": "Optional caveat, warning or tip.",
      "is_end": false
    }
  ],
  "transitions": [
    {
      "from": "page_received",
      "to": "acknowledge",
      "label": "Acknowledge the page",
      "description": "Optional explanation of what this choice means."
    }
  ]
}
```

Field limits: `title` 1-120 chars, state `id` matches `^[a-z0-9][a-z0-9_-]*$`
(max 40), `name` 1-80, `description` 1-2000, at most 50 states and 200
transitions. `description`, `annotation` and `is_end` are optional.

## 2. Satisfy the graph rules

The validator enforces these; a spec that breaks one will not render.

- `initial` and every transition `from`/`to` must name a declared state (E1, E2).
- State ids are unique (E3), and two transitions out of the same state must not
  share a label (E4).
- No transition may point at its own state (E5).
- Every state that is not an end state needs at least one outgoing transition (E6).
- At least one end state must be reachable from `initial` (E7), and every
  reachable non-end state must be able to reach an end state (E8).
- A state unreachable from `initial` is a warning, not an error (W1).

End states may still have outgoing transitions, so loops back for re-exploration
are fine.

## 3. Validate, then render

```bash
python3 -m walkforge validate flow.json   # exit 0 clean, 1 with errors on stderr
python3 -m walkforge render flow.json     # writes flow.html next to the spec
```

Each error is prefixed with its rule code. Fix the spec and re-run `validate`
until it exits 0; only then render. Warnings print to stderr but still render.

## Writing advice

Aim for 4-12 states. Every description should answer "where am I and what is
happening"; every transition label should be the reader's own choice, short and
imperative ("Roll back the deploy", not "Option A"). Include at least one real
branch — a straight line of steps is a list, not a walkthrough — and prefer
honest decision points over tidy ones.
