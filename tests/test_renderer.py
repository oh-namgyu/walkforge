"""Tests for the HTML renderer, its escaping contract and the render command."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from typing import Any, Dict, List, Tuple

from walkforge import renderer, template
from walkforge.layout import compute_layout
from walkforge.renderer import (
    default_output_path,
    embed_json,
    esc,
    fit_label,
    render_spec,
    write_document,
)
from walkforge.scaffold import example_spec
from walkforge.spec import validate_spec

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_BLOCK = re.compile(
    r'<script type="application/json" id="spec-data">(.*?)</script>', re.DOTALL
)

HOSTILE_NAME = "</script><img src=x onerror=alert(1)>"
HOSTILE_LABEL = "<img src=x onerror=alert(2)>"
HOSTILE_TEXT = "<!--\x00\x07 & \"quotes\" 'single' <b>bold</b> ‮RTL​​"


def hostile_spec() -> Dict[str, Any]:
    """A structurally valid spec whose free text tries to break out."""
    return {
        "title": "</script><!--" + HOSTILE_LABEL,
        "description": HOSTILE_TEXT,
        "initial": "start",
        "states": [
            {
                "id": "start",
                "name": HOSTILE_NAME,
                "description": HOSTILE_TEXT,
                "annotation": "</SCRIPT > <!-- " + HOSTILE_LABEL,
            },
            {"id": "done", "name": HOSTILE_TEXT[:60], "description": HOSTILE_TEXT, "is_end": True},
        ],
        "transitions": [
            {"from": "start", "to": "done", "label": HOSTILE_LABEL, "description": HOSTILE_TEXT}
        ],
    }


def render(spec: Dict[str, Any]) -> str:
    """Render a spec through the same path the CLI uses."""
    return render_spec(spec, compute_layout(spec))


def embedded(document: str) -> Any:
    """Return the spec parsed back out of the embedded JSON block."""
    found = DATA_BLOCK.search(document)
    assert found is not None, "no embedded spec block"
    return json.loads(found.group(1))


class TagCollector(HTMLParser):
    """Collect element names and every attribute seen while parsing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: List[str] = []
        self.attributes: List[Tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.tags.append(tag)
        for name, value in attrs:
            self.attributes.append((name, value or ""))


def parse(document: str) -> TagCollector:
    """Run the document through the standard library HTML parser."""
    collector = TagCollector()
    collector.feed(document)
    collector.close()
    return collector


class EscapingTest(unittest.TestCase):
    """The central esc() helper and the embedded JSON block."""

    def test_esc_escapes_markup_characters(self) -> None:
        self.assertEqual("&lt;b&gt;&amp;&quot;&#x27;", esc("<b>&\"'"))

    def test_esc_strips_controls_and_invisibles(self) -> None:
        self.assertEqual("ab", esc("a\x00\x07b​‮"))
        self.assertEqual("a b", esc("a\nb"))

    def test_embedded_json_has_no_angle_brackets(self) -> None:
        text = embed_json(hostile_spec())
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)
        self.assertNotIn("&", text)

    def test_embedded_json_round_trips(self) -> None:
        for spec in (example_spec(), hostile_spec()):
            self.assertEqual(spec, embedded(render(spec)))

    def test_fit_label_truncates_with_an_ellipsis(self) -> None:
        self.assertEqual("Short", fit_label("Short", 260))
        long_name = "n" * 60
        shortened = fit_label(long_name, 260)
        self.assertTrue(shortened.endswith("…"))
        self.assertLess(len(shortened), len(long_name))
        self.assertNotIn(long_name, render(example_spec()))


class HostileContentTest(unittest.TestCase):
    """Nothing in the spec may become active markup."""

    def setUp(self) -> None:
        self.spec = hostile_spec()
        self.document = render(self.spec)

    def test_no_image_element_appears(self) -> None:
        self.assertNotIn("<img", self.document.lower())
        self.assertNotIn("img", [tag for tag in parse(self.document).tags])
        self.assertIn("&lt;img src=x onerror=alert(2)&gt;", self.document)

    def test_exactly_two_script_elements(self) -> None:
        self.assertEqual(2, self.document.count("</script>"))
        self.assertEqual(2, parse(self.document).tags.count("script"))

    def test_no_style_or_event_attributes(self) -> None:
        for name, _value in parse(self.document).attributes:
            self.assertNotEqual("style", name)
            self.assertFalse(name.startswith("on"), name)

    def test_hostile_text_survives_escaped_in_the_title(self) -> None:
        self.assertIn("&lt;/script&gt;&lt;!--", self.document)
        self.assertNotIn("</script><!--", self.document)

    def test_hostile_spec_is_structurally_valid(self) -> None:
        self.assertEqual([], validate_spec(self.spec).errors)


class DocumentContractTest(unittest.TestCase):
    """Page-wide rules that hold for any rendered spec."""

    def setUp(self) -> None:
        self.spec = example_spec()
        self.layout = compute_layout(self.spec)
        self.document = render(self.spec)
        found = re.search(r"<svg.*?</svg>", self.document, re.DOTALL)
        assert found is not None, "no graph in the document"
        self.svg = found.group(0)

    def test_content_security_policy_is_present(self) -> None:
        self.assertIn('http-equiv="Content-Security-Policy"', self.document)
        self.assertIn("default-src 'none'", self.document)

    def test_no_inline_style_attributes(self) -> None:
        self.assertNotIn('style="', self.document)

    def test_no_remote_urls_anywhere(self) -> None:
        self.assertNotIn("http://", self.document)
        self.assertNotIn("https://", self.document)

    def test_script_never_assigns_markup(self) -> None:
        self.assertNotIn("innerHTML", template.JS)
        self.assertNotIn("innerHTML", self.document)
        self.assertNotIn("outerHTML", self.document)
        self.assertNotIn("document.write", self.document)

    def test_script_body_cannot_close_itself(self) -> None:
        self.assertNotIn("</", template.JS)
        self.assertNotIn("<!--", template.JS)
        self.assertNotIn("</", template.CSS)

    def test_graph_uses_index_based_dom_ids(self) -> None:
        for index in range(len(self.spec["states"])):
            self.assertIn('id="n%d"' % index, self.document)
        for state in self.spec["states"]:
            self.assertNotIn('id="%s"' % state["id"], self.document)

    def test_every_state_and_edge_is_drawn(self) -> None:
        self.assertEqual(len(self.spec["states"]), self.svg.count('class="node"'))
        self.assertEqual(len(self.layout.edges), self.svg.count("<polyline"))
        backward = len([edge for edge in self.layout.edges if edge.backward])
        self.assertEqual(backward, self.svg.count('class="edge edge-back"'))
        ends = len([state for state in self.spec["states"] if state.get("is_end")])
        self.assertEqual(ends, self.svg.count('data-end="1"'))

    def test_live_region_and_controls_exist(self) -> None:
        for needle in ('aria-live="polite"', 'id="restart-button"', 'id="back-button"',
                       'id="choice-list"', 'id="history-chips"', 'id="end-banner"'):
            self.assertIn(needle, self.document)

    def test_document_is_html5_and_ends_cleanly(self) -> None:
        self.assertTrue(self.document.startswith("<!doctype html>"))
        self.assertTrue(self.document.rstrip().endswith("</html>"))


class WriteDocumentTest(unittest.TestCase):
    """Atomic write behaviour."""

    def test_writes_and_returns_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "page.html")
            self.assertEqual(target, write_document(target, "hello"))
            with open(target, "r", encoding="utf-8") as handle:
                self.assertEqual("hello", handle.read())

    def test_failure_leaves_no_partial_or_temporary_file(self) -> None:
        original = renderer.os.replace

        def boom(source: str, destination: str) -> None:
            raise OSError(5, "simulated failure")

        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "page.html")
            renderer.os.replace = boom
            try:
                with self.assertRaises(OSError):
                    write_document(target, "hello")
            finally:
                renderer.os.replace = original
            self.assertEqual([], os.listdir(folder))

    def test_default_output_path_sits_next_to_the_spec(self) -> None:
        self.assertEqual(os.path.join("a", "b.html"), default_output_path(os.path.join("a", "b.json")))


class RenderCommandTest(unittest.TestCase):
    """python -m walkforge render, end to end."""

    def run_cli(self, args: List[str], cwd: str) -> Tuple[int, str, str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = REPO_ROOT + os.pathsep + environment.get("PYTHONPATH", "")
        process = subprocess.run(
            [sys.executable, "-m", "walkforge"] + args,
            cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        return process.returncode, process.stdout, process.stderr

    def write_spec(self, folder: str, spec: Dict[str, Any], name: str = "flow.json") -> str:
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(spec, handle)
        return path

    def test_render_writes_the_default_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.write_spec(folder, example_spec())
            code, out, err = self.run_cli(["render", "flow.json"], folder)
            self.assertEqual(0, code, err)
            self.assertEqual("flow.html", out.strip())
            self.assertEqual("", err)
            with open(os.path.join(folder, "flow.html"), "r", encoding="utf-8") as handle:
                self.assertEqual(example_spec(), embedded(handle.read()))

    def test_render_honours_the_output_option(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.write_spec(folder, example_spec())
            target = os.path.join(folder, "pages", "custom.html")
            os.mkdir(os.path.dirname(target))
            code, out, err = self.run_cli(["render", "flow.json", "-o", target], folder)
            self.assertEqual(0, code, err)
            self.assertEqual(target, out.strip())
            self.assertTrue(os.path.exists(target))

    def test_render_rejects_an_invalid_spec(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            spec = example_spec()
            spec["initial"] = "ghost"
            self.write_spec(folder, spec)
            code, out, err = self.run_cli(["render", "flow.json"], folder)
            self.assertEqual(1, code)
            self.assertIn("E1", err)
            self.assertEqual([], [name for name in os.listdir(folder) if name.endswith(".html")])

    def test_render_proceeds_despite_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            spec = example_spec()
            spec["states"].append(
                {"id": "island", "name": "Island", "description": "Nobody arrives.", "is_end": True}
            )
            self.write_spec(folder, spec)
            code, out, err = self.run_cli(["render", "flow.json"], folder)
            self.assertEqual(0, code)
            self.assertIn("W1", err)
            self.assertTrue(os.path.exists(os.path.join(folder, "flow.html")))


if __name__ == "__main__":
    unittest.main()
