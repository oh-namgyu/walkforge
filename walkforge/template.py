"""Static assets of the generated page: stylesheet, script and markup shell.

Everything here is literal text. The renderer supplies four already escaped
or already built fragments -- title, description, SVG graph and the embedded
JSON block -- and this module assembles the single self-contained document.

The stylesheet is the only place colours and spacing are declared: the page
carries no inline ``style`` attributes. The script never assigns markup; all
dynamic text goes through ``textContent`` and ``createElement``.
"""

from typing import List

CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"

CSS = """
:root {
  color-scheme: dark;
  --bg: #11141b;
  --bg-soft: #171c25;
  --bg-card: #1f2532;
  --fg: #e8edf7;
  --fg-dim: #97a3b6;
  --line: #2c3547;
  --line-strong: #3d4a62;
  --accent: #74b4ff;
  --accent-ink: #071120;
  --note: #f0c27a;
  --ok: #6fd39b;
  --radius: 12px;
  --gap: 16px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --bg: #f5f7fb;
    --bg-soft: #ffffff;
    --bg-card: #ffffff;
    --fg: #171d29;
    --fg-dim: #5b6779;
    --line: #d6dde9;
    --line-strong: #9fb0c8;
    --accent: #1b63c4;
    --accent-ink: #ffffff;
    --note: #8a5a00;
    --ok: #1f7a4d;
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { height: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: var(--font);
  font-size: 16px;
  line-height: 1.55;
  display: flex;
  flex-direction: column;
}
.topbar {
  display: flex;
  align-items: center;
  gap: var(--gap);
  padding: 12px 20px;
  background: var(--bg-soft);
  border-bottom: 1px solid var(--line);
}
.topbar-text { flex: 1 1 auto; min-width: 0; }
.topbar-title { margin: 0; font-size: 1.1rem; }
.topbar-subtitle { margin: 2px 0 0; color: var(--fg-dim); font-size: 0.85rem; }
.layout { flex: 1 1 auto; display: flex; min-height: 0; }
.graph-pane {
  flex: 0 0 55%;
  overflow: auto;
  padding: 20px;
  background: var(--bg);
  border-right: 1px solid var(--line);
}
.panel {
  flex: 1 1 45%;
  overflow: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  background: var(--bg-soft);
}
.panel-heading { margin: 0; font-size: 1.5rem; }
.prose { margin: 0; color: var(--fg); }
.section-title { margin: 0 0 8px; font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-dim); }
.card { border: 1px solid var(--line); border-radius: var(--radius); padding: 12px 14px; background: var(--bg-card); }
.note { border-left: 4px solid var(--note); }
.note-title { margin: 0 0 4px; font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--note); }
.banner { border: 2px double var(--ok); border-radius: var(--radius); padding: 12px 14px; background: var(--bg-card); }
.banner-title { margin: 0 0 4px; font-weight: 700; color: var(--ok); }
.banner-text { margin: 0 0 10px; color: var(--fg-dim); font-size: 0.9rem; }
.choices { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.choice {
  width: 100%;
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 4px 10px;
  text-align: left;
  font: inherit;
  color: var(--fg);
  background: var(--bg-card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 10px 12px;
  cursor: pointer;
}
.choice:hover { border-color: var(--line-strong); }
.choice:focus-visible, .btn:focus-visible, .chip:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.choice-key {
  grid-row: 1 / span 2;
  align-self: start;
  display: inline-block;
  min-width: 24px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  color: var(--fg-dim);
  font-size: 0.85rem;
}
.choice-label { font-weight: 600; }
.choice-note { color: var(--fg-dim); font-size: 0.88rem; }
.empty { margin: 0; color: var(--fg-dim); font-style: italic; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font: inherit;
  font-size: 0.85rem;
  color: var(--fg-dim);
  background: transparent;
  border: 1px dashed var(--line-strong);
  border-radius: 999px;
  padding: 2px 10px;
  cursor: pointer;
}
.chip:hover { color: var(--fg); border-style: solid; }
.controls { display: flex; align-items: center; gap: var(--gap); margin-top: auto; }
.btn {
  font: inherit;
  color: var(--fg);
  background: var(--bg-card);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  padding: 8px 14px;
  cursor: pointer;
}
.btn[disabled] { opacity: 0.45; cursor: default; }
.btn-accent { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
.step { color: var(--fg-dim); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
.hint { margin: 0; color: var(--fg-dim); font-size: 0.8rem; }
.graph { display: block; margin: 0 auto; max-width: 100%; height: auto; }
.node-box { fill: var(--bg-card); stroke: var(--line-strong); stroke-width: 1.5; }
.node-inner { fill: none; stroke: none; }
.node-label { fill: var(--fg); font-family: var(--font); font-size: 14px; font-weight: 600; }
.node[data-end="1"] .node-inner { stroke: var(--line-strong); stroke-width: 1; }
.node[data-state="visited"] .node-box { stroke-dasharray: 5 3; opacity: 0.65; }
.node[data-state="visited"] .node-label { opacity: 0.65; }
.node[data-state="current"] .node-box { stroke: var(--accent); stroke-width: 4; fill: var(--bg-soft); }
.node[data-state="current"] .node-label { fill: var(--accent); }
.badge-now, .badge-check { display: none; }
.node[data-state="current"] .badge-now { display: block; }
.node[data-state="visited"] .badge-check { display: block; }
.badge-box { fill: var(--accent); }
.badge-text { fill: var(--accent-ink); font-family: var(--font); font-size: 11px; font-weight: 700; letter-spacing: 0.06em; }
.badge-check { fill: var(--ok); font-family: var(--font); font-size: 13px; font-weight: 700; }
.edge-line { fill: none; stroke: var(--line-strong); stroke-width: 2; }
.edge-back .edge-line { stroke-dasharray: 7 5; }
.edge[data-active="1"] .edge-line { stroke: var(--accent); stroke-width: 3; }
.arrow-head { fill: var(--line-strong); }
.edge[data-active="1"] .arrow-head { fill: var(--accent); }
@media (max-width: 720px) {
  .layout { flex-direction: column; }
  .graph-pane { flex: 0 0 auto; max-height: 45vh; border-right: none; border-bottom: 1px solid var(--line); }
  .panel { flex: 1 1 auto; }
}
"""

JS = """
(function () {
  "use strict";
  var spec = JSON.parse(document.getElementById("spec-data").textContent);
  var states = spec.states;
  var byId = {};
  var indexById = {};
  var outgoing = {};
  var i;
  for (i = 0; i < states.length; i++) {
    byId[states[i].id] = states[i];
    indexById[states[i].id] = i;
  }
  for (i = 0; i < spec.transitions.length; i++) {
    var move = spec.transitions[i];
    if (!outgoing[move.from]) { outgoing[move.from] = []; }
    outgoing[move.from].push(move);
  }
  var current = spec.initial;
  var trail = [];
  var el = {};
  var ids = ["state-name", "state-description", "annotation-card", "annotation-text",
    "choice-list", "no-choices", "history-row", "history-chips", "back-button",
    "restart-button", "banner-restart", "end-banner", "step-counter"];
  for (i = 0; i < ids.length; i++) { el[ids[i]] = document.getElementById(ids[i]); }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function span(className, text) {
    var node = document.createElement("span");
    node.className = className;
    node.textContent = text;
    return node;
  }

  function choices() { return outgoing[current] || []; }

  function choose(position) {
    var list = choices();
    if (position < 0 || position >= list.length) { return; }
    trail.push(current);
    current = list[position].to;
    render();
  }

  function back() {
    if (!trail.length) { return; }
    current = trail.pop();
    render();
  }

  function jump(position) {
    if (position < 0 || position >= trail.length) { return; }
    current = trail[position];
    trail = trail.slice(0, position);
    render();
  }

  function restart() {
    current = spec.initial;
    trail = [];
    render();
  }

  function renderPanel() {
    var state = byId[current];
    el["state-name"].textContent = state.name;
    el["state-description"].textContent = state.description;
    if (state.annotation) {
      el["annotation-text"].textContent = state.annotation;
      el["annotation-card"].hidden = false;
    } else {
      el["annotation-text"].textContent = "";
      el["annotation-card"].hidden = true;
    }
    el["end-banner"].hidden = !state.is_end;
    el["step-counter"].textContent = "Step " + (trail.length + 1);
    el["back-button"].disabled = trail.length === 0;
  }

  function renderChoices() {
    var list = choices();
    clear(el["choice-list"]);
    el["no-choices"].hidden = list.length > 0;
    for (var k = 0; k < list.length; k++) {
      var item = document.createElement("li");
      var control = document.createElement("button");
      control.type = "button";
      control.className = "choice";
      control.setAttribute("data-choice", String(k));
      control.appendChild(span("choice-key", k < 9 ? String(k + 1) : "\\u2022"));
      control.appendChild(span("choice-label", list[k].label));
      if (list[k].description) {
        control.appendChild(span("choice-note", list[k].description));
      }
      control.addEventListener("click", pick(k));
      item.appendChild(control);
      el["choice-list"].appendChild(item);
    }
  }

  function pick(position) { return function () { choose(position); }; }
  function rewind(position) { return function () { jump(position); }; }

  function renderTrail() {
    clear(el["history-chips"]);
    el["history-row"].hidden = trail.length === 0;
    for (var k = 0; k < trail.length; k++) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.setAttribute("data-step", String(k));
      chip.textContent = byId[trail[k]].name;
      chip.addEventListener("click", rewind(k));
      el["history-chips"].appendChild(chip);
    }
  }

  function renderGraph() {
    var seen = {};
    var k;
    for (k = 0; k < trail.length; k++) { seen[trail[k]] = true; }
    for (k = 0; k < states.length; k++) {
      var group = document.getElementById("n" + k);
      if (!group) { continue; }
      if (states[k].id === current) {
        group.setAttribute("data-state", "current");
        group.setAttribute("aria-current", "step");
      } else {
        group.setAttribute("data-state", seen[states[k].id] ? "visited" : "idle");
        group.removeAttribute("aria-current");
      }
    }
    var here = String(indexById[current]);
    var edges = document.querySelectorAll(".edge");
    for (k = 0; k < edges.length; k++) {
      edges[k].setAttribute("data-active", edges[k].getAttribute("data-from") === here ? "1" : "0");
    }
    var node = document.getElementById("n" + indexById[current]);
    if (node && node.scrollIntoView) {
      node.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  function render() {
    renderPanel();
    renderChoices();
    renderTrail();
    renderGraph();
  }

  el["restart-button"].addEventListener("click", restart);
  el["banner-restart"].addEventListener("click", restart);
  el["back-button"].addEventListener("click", back);
  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) { return; }
    var key = event.key;
    if (key >= "1" && key <= "9") {
      choose(parseInt(key, 10) - 1);
      event.preventDefault();
    } else if (key === "Backspace" || key === "ArrowLeft") {
      back();
      event.preventDefault();
    } else if (key === "r" || key === "R") {
      restart();
      event.preventDefault();
    }
  });
  render();
}());
"""

_PANEL = """  <section class="panel" id="panel" aria-live="polite">
    <h2 class="panel-heading" id="state-name"></h2>
    <p class="prose" id="state-description"></p>
    <aside class="card note" id="annotation-card" hidden>
      <p class="note-title">Note</p>
      <p class="prose" id="annotation-text"></p>
    </aside>
    <div class="banner" id="end-banner" role="status" hidden>
      <p class="banner-title">You reached an end state.</p>
      <p class="banner-text">Keep exploring if choices remain, or start over.</p>
      <button type="button" class="btn btn-accent" id="banner-restart">Start over</button>
    </div>
    <div>
      <h3 class="section-title" id="choices-title">What happens next</h3>
      <ol class="choices" id="choice-list" aria-labelledby="choices-title"></ol>
      <p class="empty" id="no-choices" hidden>No choices lead out of this step.</p>
    </div>
    <nav class="history" id="history-row" aria-label="Path so far" hidden>
      <h3 class="section-title">Path so far</h3>
      <div class="chips" id="history-chips"></div>
    </nav>
    <div class="controls">
      <button type="button" class="btn" id="back-button">Back</button>
      <span class="step" id="step-counter"></span>
    </div>
    <p class="hint">Keys: 1-9 choose a step, Backspace goes back, R restarts.</p>
  </section>
"""


def build_document(title: str, description: str, svg: str, data_json: str) -> str:
    """Assemble the page from pre-escaped text and pre-built fragments."""
    parts: List[str] = [
        "<!doctype html>\n<html lang=\"en\">\n<head>\n",
        "<meta charset=\"utf-8\">\n",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n",
        "<meta http-equiv=\"Content-Security-Policy\" content=\"" + CSP + "\">\n",
        "<title>" + title + "</title>\n<style>" + CSS + "</style>\n</head>\n<body>\n",
        "<header class=\"topbar\">\n  <div class=\"topbar-text\">\n",
        "    <h1 class=\"topbar-title\">" + title + "</h1>\n",
    ]
    if description:
        parts.append("    <p class=\"topbar-subtitle\">" + description + "</p>\n")
    parts.append("  </div>\n  <button type=\"button\" class=\"btn\" id=\"restart-button\">Restart</button>\n")
    parts.append("</header>\n<main class=\"layout\">\n")
    parts.append("  <section class=\"graph-pane\" id=\"graph-pane\" aria-label=\"State graph\">\n")
    parts.append(svg)
    parts.append("  </section>\n")
    parts.append(_PANEL)
    parts.append("</main>\n")
    parts.append("<script type=\"application/json\" id=\"spec-data\">" + data_json + "</script>\n")
    parts.append("<script>" + JS + "</script>\n</body>\n</html>\n")
    return "".join(parts)
