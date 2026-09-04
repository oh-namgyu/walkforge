"""Tests for the scaffold template and the command line interface."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from typing import List, Tuple

from walkforge.layout import compute_layout
from walkforge.scaffold import DEFAULT_FILENAME, example_spec, target_path, write_scaffold
from walkforge.spec import load_spec, validate_spec

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def run_cli(args: List[str], cwd: str) -> Tuple[int, str, str]:
    """Run ``python -m walkforge`` and return (exit code, stdout, stderr)."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = REPO_ROOT + os.pathsep + environment.get("PYTHONPATH", "")
    process = subprocess.run(
        [sys.executable, "-m", "walkforge"] + args,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return process.returncode, process.stdout, process.stderr


class ScaffoldTest(unittest.TestCase):
    """The shipped template must survive its own validator."""

    def test_template_validates_without_errors_or_warnings(self) -> None:
        result = validate_spec(example_spec())
        self.assertEqual([], result.errors)
        self.assertEqual([], result.warnings)

    def test_template_has_a_branch_a_loop_and_two_end_states(self) -> None:
        spec = example_spec()
        self.assertEqual(6, len(spec["states"]))
        ends = [entry for entry in spec["states"] if entry.get("is_end")]
        self.assertEqual(2, len(ends))
        layout = compute_layout(spec)
        self.assertTrue(any(edge.backward for edge in layout.edges))
        self.assertTrue(any(len(layout.layers[index]) > 1 for index in range(len(layout.layers))))

    def test_written_file_round_trips_through_load_spec(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "generated.json")
            self.assertEqual(path, write_scaffold(path))
            self.assertEqual(example_spec(), load_spec(path))

    def test_extension_is_appended_once(self) -> None:
        self.assertEqual("plan.json", target_path("plan"))
        self.assertEqual("plan.json", target_path("plan.json"))
        self.assertEqual(DEFAULT_FILENAME, target_path(DEFAULT_FILENAME))

    def test_existing_file_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "taken.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("keep me")
            with self.assertRaises(FileExistsError):
                write_scaffold(path)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual("keep me", handle.read())


class CommandLineTest(unittest.TestCase):
    """End to end behaviour of python -m walkforge."""

    def test_init_creates_a_valid_spec(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            code, out, err = run_cli(["init"], folder)
            self.assertEqual(0, code, err)
            self.assertEqual(DEFAULT_FILENAME, out.strip())
            with open(os.path.join(folder, DEFAULT_FILENAME), "r", encoding="utf-8") as handle:
                self.assertEqual([], validate_spec(json.load(handle)).errors)

    def test_init_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(0, run_cli(["init", "flow"], folder)[0])
            code, out, err = run_cli(["init", "flow"], folder)
            self.assertEqual(1, code)
            self.assertEqual("", out)
            self.assertIn("refusing to overwrite", err)

    def test_validate_accepts_a_good_spec(self) -> None:
        code, out, err = run_cli(["validate", os.path.join(FIXTURES, "valid_minimal.json")], REPO_ROOT)
        self.assertEqual(0, code, err)
        self.assertEqual("", err)

    def test_validate_rejects_a_bad_spec(self) -> None:
        code, out, err = run_cli(["validate", os.path.join(FIXTURES, "invalid_e1.json")], REPO_ROOT)
        self.assertEqual(1, code)
        self.assertIn("E1", err)

    def test_validate_reports_warnings_but_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            spec = example_spec()
            spec["states"].append(
                {"id": "island", "name": "Island", "description": "Nobody gets here.", "is_end": True}
            )
            path = os.path.join(folder, "warned.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(spec, handle)
            code, out, err = run_cli(["validate", path], folder)
        self.assertEqual(0, code)
        self.assertIn("W1", err)

    def test_every_subcommand_is_registered(self) -> None:
        code, out, err = run_cli(["--help"], REPO_ROOT)
        self.assertEqual(0, code, err)
        for name in ("init", "validate", "render", "new", "revise"):
            self.assertIn(name, out)

    def test_no_command_prints_help(self) -> None:
        code, out, err = run_cli([], REPO_ROOT)
        self.assertEqual(2, code)
        self.assertIn("usage", err)

    def test_version_flag(self) -> None:
        code, out, err = run_cli(["--version"], REPO_ROOT)
        self.assertEqual(0, code, err)
        self.assertIn("walkforge", out + err)


if __name__ == "__main__":
    unittest.main()
