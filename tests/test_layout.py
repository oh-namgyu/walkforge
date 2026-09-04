"""Tests for the BFS layered layout engine."""

import unittest
from typing import Any, Dict, List, Sequence, Tuple

from walkforge.layout import (
    LAYER_GAP,
    NODE_HEIGHT,
    NODE_MAX_WIDTH,
    NODE_MIN_WIDTH,
    EdgeRoute,
    Layout,
    compute_layout,
    node_width,
)
from walkforge.spec import validate_spec


def state(state_id: str, is_end: bool = False, name: str = "") -> Dict[str, Any]:
    """Build a valid state entry."""
    entry: Dict[str, Any] = {
        "id": state_id,
        "name": name or state_id.replace("_", " ").title(),
        "description": "Step %s." % state_id,
    }
    if is_end:
        entry["is_end"] = True
    return entry


def spec_of(
    states: Sequence[Dict[str, Any]], pairs: Sequence[Tuple[str, str, str]], initial: str = "a"
) -> Dict[str, Any]:
    """Build a spec from states and (from, to, label) triples."""
    return {
        "title": "Shape under test",
        "initial": initial,
        "states": list(states),
        "transitions": [{"from": src, "to": dst, "label": label} for src, dst, label in pairs],
    }


def linear_spec() -> Dict[str, Any]:
    """a -> b -> c(end)."""
    return spec_of(
        [state("a"), state("b"), state("c", is_end=True)],
        [("a", "b", "Next"), ("b", "c", "Finish")],
    )


def branch_spec() -> Dict[str, Any]:
    """a branches into b and c, both end states."""
    return spec_of(
        [state("a"), state("b", is_end=True), state("c", is_end=True)],
        [("a", "b", "Left"), ("a", "c", "Right")],
    )


def merge_spec() -> Dict[str, Any]:
    """a -> b and a -> c, both merging into d(end)."""
    return spec_of(
        [state("a"), state("b"), state("c"), state("d", is_end=True)],
        [("a", "b", "Left"), ("a", "c", "Right"), ("b", "d", "Join"), ("c", "d", "Join")],
    )


def backward_spec() -> Dict[str, Any]:
    """a -> b -> c(end) with b looping back to a."""
    return spec_of(
        [state("a"), state("b"), state("c", is_end=True)],
        [("a", "b", "Next"), ("b", "c", "Finish"), ("b", "a", "Back")],
    )


def unreachable_spec() -> Dict[str, Any]:
    """linear chain plus an island that nothing points at."""
    spec = linear_spec()
    spec["states"].append(state("island", is_end=True))
    return spec


def flags(layout: Layout) -> List[Tuple[str, str, bool]]:
    """Return (from, to, backward) for every routed edge, in order."""
    return [(edge.from_id, edge.to_id, edge.backward) for edge in layout.edges]


class LayoutInvariantMixin(unittest.TestCase):
    """Shared assertions every layout must satisfy."""

    def assert_sane(self, layout: Layout) -> None:
        for state_id, box in layout.nodes.items():
            self.assertEqual(4, len(box), state_id)
            for value in box:
                self.assertIsInstance(value, int)
            self.assertEqual(NODE_HEIGHT, box[3])
            self.assertTrue(NODE_MIN_WIDTH <= box[2] <= NODE_MAX_WIDTH)
            self.assertTrue(0 <= box[0] and box[0] + box[2] <= layout.width)
            self.assertTrue(0 <= box[1] and box[1] + box[3] <= layout.height)
        tops = [layout.nodes[layer[0]][1] for layer in layout.layers]
        self.assertEqual(sorted(set(tops)), tops)
        for index, layer in enumerate(layout.layers):
            for state_id in layer:
                self.assertEqual(tops[index], layout.nodes[state_id][1])
        for edge in layout.edges:
            self.assertTrue(len(edge.points) >= 2)
            for point in edge.points:
                self.assertIsInstance(point[0], int)
                self.assertIsInstance(point[1], int)


class GoldenShapeTest(LayoutInvariantMixin):
    """Golden expectations for four canonical graph shapes."""

    def test_linear_chain(self) -> None:
        layout = compute_layout(linear_spec())
        self.assertEqual([["a"], ["b"], ["c"]], layout.layers)
        self.assertEqual([("a", "b", False), ("b", "c", False)], flags(layout))
        self.assert_sane(layout)

    def test_branch(self) -> None:
        layout = compute_layout(branch_spec())
        self.assertEqual([["a"], ["b", "c"]], layout.layers)
        self.assertEqual([("a", "b", False), ("a", "c", False)], flags(layout))
        self.assertLess(layout.nodes["b"][0], layout.nodes["c"][0])
        self.assert_sane(layout)

    def test_merge(self) -> None:
        layout = compute_layout(merge_spec())
        self.assertEqual([["a"], ["b", "c"], ["d"]], layout.layers)
        self.assertEqual(
            [("a", "b", False), ("a", "c", False), ("b", "d", False), ("c", "d", False)],
            flags(layout),
        )
        self.assert_sane(layout)

    def test_backward_edge(self) -> None:
        layout = compute_layout(backward_spec())
        self.assertEqual([["a"], ["b"], ["c"]], layout.layers)
        self.assertEqual(
            [("a", "b", False), ("b", "c", False), ("b", "a", True)], flags(layout)
        )
        loop = layout.edges[2]
        self.assertEqual(4, len(loop.points))
        self.assertTrue(max(point[0] for point in loop.points) > layout.nodes["b"][0])
        self.assert_sane(layout)

    def test_layer_tops_increase_by_a_fixed_step(self) -> None:
        layout = compute_layout(linear_spec())
        tops = [layout.nodes[layer[0]][1] for layer in layout.layers]
        self.assertEqual(NODE_HEIGHT + LAYER_GAP, tops[1] - tops[0])
        self.assertEqual(NODE_HEIGHT + LAYER_GAP, tops[2] - tops[1])

    def test_forward_edge_has_at_most_one_bend(self) -> None:
        layout = compute_layout(merge_spec())
        for edge in layout.edges:
            if not edge.backward:
                self.assertIn(len(edge.points), (2, 3))


class UnreachableStateTest(LayoutInvariantMixin):
    """Specs that only produced warnings must still lay out."""

    def test_island_goes_to_the_bottom_layer(self) -> None:
        spec = unreachable_spec()
        result = validate_spec(spec)
        self.assertEqual([], result.errors)
        self.assertEqual(1, len(result.warnings))
        layout = compute_layout(spec)
        self.assertEqual([["a"], ["b"], ["c"], ["island"]], layout.layers)
        self.assert_sane(layout)

    def test_missing_initial_still_lays_out(self) -> None:
        spec = linear_spec()
        spec["initial"] = "ghost"
        layout = compute_layout(spec)
        self.assertEqual([["a", "b", "c"]], layout.layers)
        self.assert_sane(layout)


class DeterminismTest(unittest.TestCase):
    """The same spec dict must always produce identical geometry."""

    def fingerprint(self, layout: Layout) -> str:
        parts = ["%s=%r" % (key, layout.nodes[key]) for key in sorted(layout.nodes)]
        parts += ["%s>%s:%r:%r" % (e.from_id, e.to_id, e.points, e.backward) for e in layout.edges]
        parts.append("%dx%d" % (layout.width, layout.height))
        return "|".join(parts)

    def test_repeated_runs_match(self) -> None:
        for builder in (linear_spec, branch_spec, merge_spec, backward_spec, unreachable_spec):
            first = self.fingerprint(compute_layout(builder()))
            second = self.fingerprint(compute_layout(builder()))
            self.assertEqual(first, second, builder.__name__)


class NodeSizeTest(unittest.TestCase):
    """Box width tracks the name length inside fixed bounds."""

    def test_short_name_hits_the_minimum(self) -> None:
        self.assertEqual(NODE_MIN_WIDTH, node_width("A"))

    def test_long_name_hits_the_maximum(self) -> None:
        self.assertEqual(NODE_MAX_WIDTH, node_width("n" * 200))

    def test_width_is_monotonic(self) -> None:
        widths = [node_width("n" * length) for length in range(1, 40)]
        self.assertEqual(widths, sorted(widths))
        self.assertLess(node_width("short"), node_width("a considerably longer state name"))

    def test_edge_route_keeps_its_label(self) -> None:
        route = EdgeRoute("a", "b", "Next", [(0, 0), (1, 1)], False)
        self.assertEqual("Next", route.label)
        self.assertIn("a", repr(route))


if __name__ == "__main__":
    unittest.main()
