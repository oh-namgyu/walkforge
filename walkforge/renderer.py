"""Turn a validated spec plus its layout into one self-contained HTML page.

Every piece of spec text that reaches the markup passes through ``esc``:
control characters and invisible formatting characters are dropped, then the
result is HTML escaped. The spec itself is embedded verbatim as JSON with all
non-ASCII and all angle brackets escaped, so the data block can never end its
own script element or start a comment.
"""

import json
import os
import tempfile
from typing import Any, Dict, List, Sequence, Tuple

from .layout import CHAR_WIDTH, LABEL_PADDING, Box, EdgeRoute, Layout
from .template import build_document

ELLIPSIS = "…"

# C0/C1 controls (tab, newline and carriage return become spaces) plus the
# bidirectional overrides and zero width characters used to disguise text.
_INVISIBLE = (
    list(range(0x00, 0x20))
    + [0x7F]
    + list(range(0x80, 0xA0))
    + [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF]
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A))
)
_CLEAN_MAP: Dict[int, Any] = dict((code, None) for code in _INVISIBLE)
for _space in (0x09, 0x0A, 0x0D):
    _CLEAN_MAP[_space] = " "

_ESCAPES: List[Tuple[str, str]] = [
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#x27;"),
]


def esc(value: Any) -> str:
    """Strip invisible characters from ``value`` and HTML escape the rest."""
    text = value if isinstance(value, str) else str(value)
    text = text.translate(_CLEAN_MAP)
    for needle, replacement in _ESCAPES:
        text = text.replace(needle, replacement)
    return text


def fit_label(name: str, width: int) -> str:
    """Shorten a state name to what its box can show, adding an ellipsis."""
    room = max(1, (width - 2 * LABEL_PADDING) // CHAR_WIDTH)
    if len(name) <= room:
        return name
    return name[: max(1, room - 1)] + ELLIPSIS


def _attrs(pairs: Sequence[Tuple[str, Any]]) -> str:
    """Render an attribute list, escaping every value."""
    return "".join(' %s="%s"' % (name, esc(value)) for name, value in pairs)


def _defs() -> str:
    """Arrow head markers for plain and backward edges."""
    shape = '<path class="arrow-head" d="M0,0 L8,3 L0,6 z"/>'
    marker = (
        '<marker id="%s" markerWidth="8" markerHeight="6" refX="8" refY="3" '
        'orient="auto" markerUnits="userSpaceOnUse">%s</marker>'
    )
    return "<defs>" + (marker % ("wf-arrow", shape)) + (marker % ("wf-arrow-back", shape)) + "</defs>"


def _edge_markup(edge: EdgeRoute, index_of: Dict[str, int]) -> str:
    """One edge: a group carrying its label as a tooltip plus the polyline."""
    points = " ".join("%d,%d" % (x, y) for x, y in edge.points)
    marker = "wf-arrow-back" if edge.backward else "wf-arrow"
    group = _attrs(
        [
            ("class", "edge edge-back" if edge.backward else "edge"),
            ("data-from", index_of[edge.from_id]),
            ("data-to", index_of[edge.to_id]),
            ("data-active", "0"),
        ]
    )
    line = _attrs([("class", "edge-line"), ("points", points), ("marker-end", "url(#%s)" % marker)])
    return "<g%s><title>%s</title><polyline%s/></g>" % (group, esc(edge.label), line)


def _badge_markup(box: Box) -> str:
    """The NOW badge and the visited check mark, both hidden by default."""
    x, y, width, height = box
    badge = _attrs([("class", "badge-box"), ("x", x + width - 46), ("y", y - 10), ("width", 42), ("height", 20), ("rx", 10)])
    text = _attrs([("class", "badge-text"), ("x", x + width - 25), ("y", y + 4), ("text-anchor", "middle")])
    check = _attrs([("class", "badge-check"), ("x", x + 12), ("y", y + height - 10)])
    return (
        '<g class="badge-now"><rect%s/><text%s>NOW</text></g><text%s>✓</text>'
        % (badge, text, check)
    )


def _node_markup(index: int, state: Dict[str, Any], box: Box) -> str:
    """One state: outer box, inner box for end states, label and badges."""
    x, y, width, height = box
    group = _attrs(
        [
            ("class", "node"),
            ("id", "n%d" % index),
            ("data-state", "idle"),
            ("data-end", "1" if state.get("is_end", False) else "0"),
        ]
    )
    outer = _attrs([("class", "node-box"), ("x", x), ("y", y), ("width", width), ("height", height), ("rx", 12)])
    inner = _attrs(
        [("class", "node-inner"), ("x", x + 5), ("y", y + 5), ("width", width - 10), ("height", height - 10), ("rx", 8)]
    )
    label = _attrs([("class", "node-label"), ("x", x + width // 2), ("y", y + height // 2 + 5), ("text-anchor", "middle")])
    return "<g%s><rect%s/><rect%s/><text%s>%s</text>%s</g>" % (
        group,
        outer,
        inner,
        label,
        esc(fit_label(state["name"], width)),
        _badge_markup(box),
    )


def build_svg(spec: Dict[str, Any], layout: Layout) -> str:
    """Build the whole graph as inline SVG, edges first so nodes sit on top."""
    states: Sequence[Dict[str, Any]] = spec["states"]
    index_of = dict((state["id"], index) for index, state in enumerate(states))
    opening = _attrs(
        [
            ("class", "graph"),
            ("viewBox", "0 0 %d %d" % (layout.width, layout.height)),
            ("width", layout.width),
            ("height", layout.height),
            ("role", "group"),
            ("aria-label", "Walkthrough state graph"),
        ]
    )
    parts: List[str] = ["<svg%s>" % opening, _defs(), '<g class="edges">']
    for edge in layout.edges:
        parts.append(_edge_markup(edge, index_of))
    parts.append('</g><g class="nodes">')
    for index, state in enumerate(states):
        box = layout.nodes.get(state["id"])
        if box is not None:
            parts.append(_node_markup(index, state, box))
    parts.append("</g></svg>\n")
    return "".join(parts)


def embed_json(spec: Dict[str, Any]) -> str:
    """Serialise the spec so it cannot break out of its script element."""
    text = json.dumps(spec, ensure_ascii=True, sort_keys=False, separators=(",", ":"))
    for needle, replacement in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(needle, replacement)
    return text


def render_spec(spec: Dict[str, Any], layout: Layout) -> str:
    """Return the complete walkthrough page for a spec and its layout."""
    return build_document(
        esc(spec["title"]),
        esc(spec.get("description", "")),
        build_svg(spec, layout),
        embed_json(spec),
    )


def default_output_path(spec_path: str) -> str:
    """Return ``<spec name>.html`` next to the spec file."""
    return os.path.splitext(spec_path)[0] + ".html"


def _default_file_mode() -> int:
    """Return the permission bits a normal new file would get."""
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def write_document(path: str, text: str) -> str:
    """Write ``text`` to ``path`` atomically, leaving no partial file behind."""
    folder = os.path.dirname(os.path.abspath(path)) or "."
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=folder, prefix=".walkforge-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            handle.write(text)
        os.chmod(handle.name, _default_file_mode())
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    return path
