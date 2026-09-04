"""Tests for the two model-backed commands: new and revise."""

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from typing import Any, Callable, Dict, Tuple
from unittest import mock

from stubs import Reply, as_reply, broken_spec, stubbed

from walkforge import commands, llm
from walkforge.scaffold import example_spec

SLUG = "incident-response-walkthrough"


def call(function: Callable[..., int], *args: Any) -> Tuple[int, str, str]:
    """Run a command function, capturing its exit code and streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = function(*args)
    return code, out.getvalue(), err.getvalue()


def read_json(path: str) -> Dict[str, Any]:
    """Read a JSON document from disk."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, data: Dict[str, Any]) -> str:
    """Write a JSON document to disk."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return path


class NamingTest(unittest.TestCase):
    """Slugs and the non-clobbering name picker."""

    def test_slugify(self) -> None:
        self.assertEqual(SLUG, commands.slugify("Incident response walkthrough"))
        self.assertEqual("cafe-au-lait", commands.slugify("Café  au   lait!"))
        self.assertEqual("walkthrough", commands.slugify("???"))
        long_slug = commands.slugify("word " * 40)
        self.assertLessEqual(len(long_slug), 60)
        self.assertFalse(long_slug.endswith("-"))

    def test_unique_path_numbers_from_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "flow.json")
            self.assertEqual(first, commands.unique_path(first))
            write_json(first, {})
            second = commands.unique_path(first)
            self.assertEqual(os.path.join(folder, "flow-2.json"), second)
            write_json(second, {})
            self.assertEqual(os.path.join(folder, "flow-3.json"), commands.unique_path(first))


class NewCommandTest(unittest.TestCase):
    """walkforge new: generate, repair once, write, render."""

    def test_happy_path_writes_spec_and_page(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with stubbed(as_reply(example_spec())) as client:
                code, out, err = call(commands.command_new, "An outage", folder, None, False)
            self.assertEqual(0, code, err)
            self.assertEqual("", err)
            self.assertEqual(1, len(client.messages.calls))
            paths = out.split()
            self.assertEqual([SLUG + ".json", SLUG + ".html"], [os.path.basename(p) for p in paths])
            self.assertEqual(example_spec(), read_json(paths[0]))
            with open(paths[1], "r", encoding="utf-8") as handle:
                self.assertIn("<!doctype html>", handle.read())

    def test_invalid_draft_is_repaired_once(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            replies = (as_reply(broken_spec()), as_reply(example_spec()))
            with stubbed(*replies) as client:
                code, out, err = call(commands.command_new, "An outage", folder, None, False)
            self.assertEqual(0, code, err)
            self.assertEqual(2, len(client.messages.calls))
            self.assertIn("E1:", client.messages.calls[1]["messages"][0]["content"])
            self.assertTrue(os.path.exists(os.path.join(folder, SLUG + ".json")))

    def test_two_bad_drafts_write_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            replies = (as_reply(broken_spec()), as_reply(broken_spec()))
            with stubbed(*replies) as client:
                code, out, err = call(commands.command_new, "An outage", folder, None, False)
            self.assertEqual(1, code)
            self.assertEqual("", out)
            self.assertIn("E1", err)
            self.assertEqual(2, len(client.messages.calls))
            self.assertEqual([], os.listdir(folder))

    def test_generation_error_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with stubbed(as_reply(example_spec(), "refusal")):
                code, out, err = call(commands.command_new, "An outage", folder, None, False)
            self.assertEqual(1, code)
            self.assertIn("generation failed", err)
            self.assertEqual([], os.listdir(folder))

    def test_debug_writes_a_private_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with stubbed(as_reply(example_spec())):
                code, out, err = call(commands.command_new, "An outage", folder, None, True)
            self.assertEqual(0, code, err)
            debug = os.path.join(folder, commands.DEBUG_FILENAME)
            self.assertTrue(os.path.exists(debug))
            self.assertEqual(0o600, stat.S_IMODE(os.stat(debug).st_mode))
            with open(debug, "r", encoding="utf-8") as handle:
                body = handle.read()
            self.assertIn("An outage", body)
            self.assertIn("alert_received", body)
            self.assertIn("delete it after debugging", err)

    def test_debug_file_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                with stubbed(as_reply(example_spec())):
                    call(commands.command_new, "An outage", folder, None, True)
            names = sorted(n for n in os.listdir(folder) if n.startswith("walkforge-debug"))
            self.assertEqual(["walkforge-debug-2.txt", "walkforge-debug.txt"], names)

    def test_debug_saves_the_transcript_even_when_generation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with stubbed(Reply("[]")):
                code, out, err = call(commands.command_new, "An outage", folder, None, True)
            self.assertEqual(1, code)
            self.assertTrue(os.path.exists(os.path.join(folder, commands.DEBUG_FILENAME)))

    def test_repeated_runs_do_not_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                with stubbed(as_reply(example_spec())):
                    code, out, err = call(commands.command_new, "An outage", folder, None, False)
                    self.assertEqual(0, code, err)
            names = sorted(os.listdir(folder))
            self.assertEqual(
                [SLUG + "-2.html", SLUG + "-2.json", SLUG + ".html", SLUG + ".json"], names
            )

    def test_overlong_situation_never_calls_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with stubbed() as client:
                code, out, err = call(
                    commands.command_new, "x" * (commands.MAX_SITUATION + 1), folder, None, False
                )
            self.assertEqual(2, code)
            self.assertIn("limit is %d" % commands.MAX_SITUATION, err)
            self.assertEqual([], client.messages.calls)
            self.assertEqual([], os.listdir(folder))

    def test_missing_key_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {}, clear=True):
                code, out, err = call(commands.command_new, "An outage", folder, None, False)
            self.assertEqual(2, code)
            self.assertIn(llm.KEY_ENV, err)
            self.assertEqual([], os.listdir(folder))

    def test_out_dir_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            nested = os.path.join(folder, "pages", "today")
            with stubbed(as_reply(example_spec())):
                code, out, err = call(commands.command_new, "An outage", nested, None, False)
            self.assertEqual(0, code, err)
            self.assertTrue(os.path.exists(os.path.join(nested, SLUG + ".json")))


class ReviseCommandTest(unittest.TestCase):
    """walkforge revise: copy-on-write by default, backup when in place."""

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = write_json(os.path.join(self.folder.name, "flow.json"), example_spec())
        self.revised = example_spec()
        self.revised["title"] = "Revised incident response"

    def test_writes_a_sibling_file_by_default(self) -> None:
        with stubbed(as_reply(self.revised)) as client:
            code, out, err = call(commands.command_revise, "Shorten it", self.path, False, None, False)
        self.assertEqual(0, code, err)
        target = os.path.join(self.folder.name, "flow.revised.json")
        self.assertEqual([target, target[:-5] + ".html"], out.split())
        self.assertEqual(self.revised, read_json(target))
        self.assertEqual(example_spec(), read_json(self.path))
        self.assertIn("Shorten it", client.messages.calls[0]["messages"][0]["content"])

    def test_sibling_file_is_numbered_when_taken(self) -> None:
        write_json(os.path.join(self.folder.name, "flow.revised.json"), {})
        with stubbed(as_reply(self.revised)):
            code, out, err = call(commands.command_revise, "Shorten it", self.path, False, None, False)
        self.assertEqual(0, code, err)
        self.assertEqual("flow.revised-2.json", os.path.basename(out.split()[0]))
        self.assertEqual({}, read_json(os.path.join(self.folder.name, "flow.revised.json")))

    def test_in_place_backs_up_first(self) -> None:
        with stubbed(as_reply(self.revised)):
            code, out, err = call(commands.command_revise, "Shorten it", self.path, True, None, False)
        self.assertEqual(0, code, err)
        self.assertEqual(self.revised, read_json(self.path))
        self.assertEqual(example_spec(), read_json(self.path + ".bak"))

    def test_existing_backup_is_never_overwritten(self) -> None:
        for _ in range(2):
            with stubbed(as_reply(self.revised)):
                code, out, err = call(
                    commands.command_revise, "Shorten it", self.path, True, None, False
                )
                self.assertEqual(0, code, err)
        self.assertEqual(example_spec(), read_json(self.path + ".bak"))
        self.assertEqual(self.revised, read_json(self.path + "-2.bak"))

    def test_invalid_input_spec_never_calls_the_model(self) -> None:
        write_json(self.path, broken_spec())
        with stubbed() as client:
            code, out, err = call(commands.command_revise, "Shorten it", self.path, False, None, False)
        self.assertEqual(1, code)
        self.assertIn("E1", err)
        self.assertEqual([], client.messages.calls)

    def test_bad_revision_leaves_the_original_alone(self) -> None:
        with stubbed(as_reply(broken_spec()), as_reply(broken_spec())):
            code, out, err = call(commands.command_revise, "Shorten it", self.path, True, None, False)
        self.assertEqual(1, code)
        self.assertEqual(example_spec(), read_json(self.path))
        self.assertFalse(os.path.exists(self.path + ".bak"))

    def test_overlong_instruction_exits_two(self) -> None:
        with stubbed() as client:
            code, out, err = call(
                commands.command_revise,
                "x" * (commands.MAX_SITUATION + 1), self.path, False, None, False,
            )
        self.assertEqual(2, code)
        self.assertEqual([], client.messages.calls)


if __name__ == "__main__":
    unittest.main()
