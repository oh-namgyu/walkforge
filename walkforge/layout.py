"""Deterministic layered layout for a validated walkthrough spec.

States are placed in horizontal layers derived from a breadth first search
from the initial state; within a layer the order is the order in which the
search first encountered each state, so the same spec always produces the
same pixel geometry. States that no search can reach (validation warning W1)
are gathered into one extra layer at the bottom.

Edges leading to a deeper layer are drawn as polylines with at most one bend.
Edges leading back to the same or a shallower layer are marked ``backward``
and routed through a vertical lane reserved on the right hand side. Only the
route points are produced here; turning them into SVG paths is the renderer's
job.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

MARGIN = 40
NODE_HEIGHT = 56
NODE_MIN_WIDTH = 140
NODE_MAX_WIDTH = 260
CHAR_WIDTH = 9
LABEL_PADDING = 32
COLUMN_GAP = 48
LAYER_GAP = 96
SIDE_LANE = 64

Box = Tuple[int, int, int, int]
Point = Tuple[int, int]


class EdgeRoute:
    """One routed transition: its endpoints, label and polyline points."""

    def __init__(
        self, from_id: str, to_id: str, label: str, points: Sequence[Point], backward: bool
    ) -> None:
        self.from_id = from_id
        self.to_id = to_id
        self.label = label
        self.points: List[Point] = [(int(x), int(y)) for x, y in points]
        self.backward = backward

    def __repr__(self) -> str:
        return "EdgeRoute(%r -> %r, backward=%r, points=%r)" % (
            self.from_id,
            self.to_id,
            self.backward,
            self.points,
        )


class Layout:
    """Positioned nodes and routed edges, plus the canvas size in pixels."""

    def __init__(
        self,
        nodes: Dict[str, Box],
        edges: Sequence[EdgeRoute],
        layers: Sequence[Sequence[str]],
        width: int,
        height: int,
    ) -> None:
        self.nodes: Dict[str, Box] = nodes
        self.edges: List[EdgeRoute] = list(edges)
        self.layers: List[List[str]] = [list(layer) for layer in layers]
        self.width = width
        self.height = height

    def level_of(self, state_id: str) -> int:
        """Return the layer index a state was placed in."""
        for index, layer in enumerate(self.layers):
            if state_id in layer:
                return index
        raise KeyError(state_id)

    def __repr__(self) -> str:
        return "Layout(nodes=%d, edges=%d, layers=%d, %dx%d)" % (
            len(self.nodes),
            len(self.edges),
            len(self.layers),
            self.width,
            self.height,
        )


def node_width(name: str) -> int:
    """Return the box width for a state name, clamped to the width bounds."""
    natural = len(name) * CHAR_WIDTH + 2 * LABEL_PADDING
    return max(NODE_MIN_WIDTH, min(NODE_MAX_WIDTH, natural))


def _edges_by_source(
    transitions: Sequence[Dict[str, Any]], known: Sequence[str]
) -> Dict[str, List[str]]:
    """Group transition targets by source, keeping declaration order."""
    known_ids = set(known)
    grouped: Dict[str, List[str]] = {}
    for transition in transitions:
        source, target = transition["from"], transition["to"]
        if source in known_ids and target in known_ids:
            grouped.setdefault(source, []).append(target)
    return grouped


def _build_layers(
    ids: Sequence[str], initial: Optional[str], grouped: Dict[str, List[str]]
) -> List[List[str]]:
    """Assign states to BFS layers; unreachable states form the last layer."""
    layers: List[List[str]] = []
    seen: List[str] = []
    if initial is not None and initial in ids:
        frontier = [initial]
        seen.append(initial)
        while frontier:
            layers.append(list(frontier))
            following: List[str] = []
            for state_id in frontier:
                for target in grouped.get(state_id, []):
                    if target not in seen:
                        seen.append(target)
                        following.append(target)
            frontier = following
    orphans = [state_id for state_id in ids if state_id not in seen]
    if orphans:
        layers.append(orphans)
    return layers


def _place_nodes(
    layers: Sequence[Sequence[str]], names: Dict[str, str]
) -> Tuple[Dict[str, Box], int, int]:
    """Centre each layer horizontally and return (boxes, width, height)."""
    widths: Dict[str, int] = {}
    layer_widths: List[int] = []
    for layer in layers:
        total = 0
        for state_id in layer:
            widths[state_id] = node_width(names[state_id])
            total += widths[state_id]
        total += COLUMN_GAP * max(0, len(layer) - 1)
        layer_widths.append(total)
    content = max(layer_widths) if layer_widths else 0
    width = content + 2 * MARGIN
    nodes: Dict[str, Box] = {}
    for index, layer in enumerate(layers):
        cursor = (width - layer_widths[index]) // 2
        top = MARGIN + index * (NODE_HEIGHT + LAYER_GAP)
        for state_id in layer:
            nodes[state_id] = (cursor, top, widths[state_id], NODE_HEIGHT)
            cursor += widths[state_id] + COLUMN_GAP
    rows = len(layers)
    height = 2 * MARGIN + rows * NODE_HEIGHT + max(0, rows - 1) * LAYER_GAP
    return nodes, width, height


def _forward_points(source: Box, target: Box) -> List[Point]:
    """Polyline from the bottom of ``source`` to the top of ``target``."""
    start = (source[0] + source[2] // 2, source[1] + source[3])
    end = (target[0] + target[2] // 2, target[1])
    if start[0] == end[0]:
        return [start, end]
    return [start, ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2), end]


def _backward_points(source: Box, target: Box, lane_x: int) -> List[Point]:
    """Route from the right of ``source`` around the lane into ``target``."""
    start = (source[0] + source[2], source[1] + source[3] // 2)
    end = (target[0] + target[2], target[1] + target[3] // 2)
    return [start, (lane_x, start[1]), (lane_x, end[1]), end]


def compute_layout(spec: Dict[str, Any]) -> Layout:
    """Lay out a spec that already passed validation (warnings are fine)."""
    states: Sequence[Dict[str, Any]] = spec.get("states", [])
    transitions: Sequence[Dict[str, Any]] = spec.get("transitions", [])
    ids: List[str] = []
    names: Dict[str, str] = {}
    for state in states:
        if state["id"] not in names:
            ids.append(state["id"])
            names[state["id"]] = state["name"]
    grouped = _edges_by_source(transitions, ids)
    layers = _build_layers(ids, spec.get("initial"), grouped)
    nodes, width, height = _place_nodes(layers, names)
    level: Dict[str, int] = {}
    for index, layer in enumerate(layers):
        for state_id in layer:
            level[state_id] = index
    routed = [
        transition
        for transition in transitions
        if transition["from"] in nodes and transition["to"] in nodes
    ]
    lane_x = width - MARGIN // 2
    if any(level[t["to"]] <= level[t["from"]] for t in routed):
        width += SIDE_LANE
    edges: List[EdgeRoute] = []
    for transition in routed:
        source, target = nodes[transition["from"]], nodes[transition["to"]]
        backward = level[transition["to"]] <= level[transition["from"]]
        points = (
            _backward_points(source, target, lane_x)
            if backward
            else _forward_points(source, target)
        )
        edges.append(
            EdgeRoute(transition["from"], transition["to"], transition["label"], points, backward)
        )
    return Layout(nodes, edges, layers, width, height)
