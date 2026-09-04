"""Command implementations behind the walkforge command line.

Exit codes are uniform across every command: 0 on success, 1 when a spec
fails validation or the model cannot produce a usable one, 2 for usage
problems (input too long, missing API key, missing optional dependency).

Nothing here overwrites a file the user already has. Specs, backups and
debug dumps all get a numbered name when their first choice is taken; only
the rendered HTML, which walkforge can always regenerate, is replaced.
"""

import json
import os
import shutil
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import llm
from .layout import compute_layout
from .renderer import default_output_path, render_spec, write_document
from .scaffold import write_scaffold
from .spec import SpecError, ValidationResult, load_spec, validate_spec

MAX_SITUATION = 8000
DEBUG_FILENAME = "walkforge-debug.txt"
DEBUG_NOTE = (
    "raw model output saved to %s -- it contains your prompt text; delete it after debugging\n"
)


def report(prefix: str, messages: Sequence[str]) -> None:
    """Print one message per line to stderr under a short heading."""
    if messages:
        sys.stderr.write("%s:\n" % prefix)
        for message in messages:
            sys.stderr.write("  %s\n" % message)


def slugify(title: str) -> str:
    """Turn a spec title into a lowercase ASCII file stem."""
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    parts: List[str] = []
    word = ""
    for char in plain.lower():
        if char.isalnum():
            word += char
        elif word:
            parts.append(word)
            word = ""
    if word:
        parts.append(word)
    return "-".join(parts)[:60].strip("-") or "walkthrough"


def unique_path(path: str) -> str:
    """Return ``path``, or the first free ``name-2.ext`` style variant."""
    if not os.path.exists(path):
        return path
    stem, extension = os.path.splitext(path)
    index = 2
    while os.path.exists("%s-%d%s" % (stem, index, extension)):
        index += 1
    return "%s-%d%s" % (stem, index, extension)


def save_debug(transcript: Sequence[str], folder: str) -> Optional[str]:
    """Write the prompt and reply transcript to a private file."""
    if not transcript:
        return None
    path = unique_path(os.path.join(folder, DEBUG_FILENAME))
    handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write("\n\n".join(transcript) + "\n")
    sys.stderr.write(DEBUG_NOTE % path)
    return path


def write_spec_and_page(spec: Dict[str, Any], json_path: str) -> str:
    """Write a spec next to its rendered page; return the page path."""
    write_document(json_path, json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    page_path = default_output_path(json_path)
    write_document(page_path, render_spec(spec, compute_layout(spec)))
    return page_path


def settle(
    spec: Dict[str, Any], model: str, transcript: Optional[List[str]]
) -> Tuple[Optional[Dict[str, Any]], ValidationResult]:
    """Validate a generated spec, allowing the model one repair attempt."""
    result = validate_spec(spec)
    if not result.errors:
        return spec, result
    repaired = llm.repair_spec(spec, result.errors, model, transcript=transcript)
    result = validate_spec(repaired)
    if result.errors:
        return None, result
    return repaired, result


def command_init(name: str) -> int:
    """Write the example spec, refusing to overwrite an existing file."""
    try:
        path = write_scaffold(name)
    except FileExistsError:
        sys.stderr.write("refusing to overwrite existing file: %s\n" % name)
        return 1
    except OSError as exc:
        sys.stderr.write("cannot write '%s': %s\n" % (name, exc.strerror or exc))
        return 1
    sys.stdout.write("%s\n" % path)
    return 0


def command_validate(path: str) -> int:
    """Validate a spec file, printing errors and warnings to stderr."""
    try:
        data = load_spec(path)
    except SpecError as exc:
        report("invalid spec", exc.messages)
        return 1
    report("warnings", validate_spec(data).warnings)
    return 0


def command_render(path: str, output: Optional[str]) -> int:
    """Validate a spec and write its walkthrough page next to it."""
    try:
        data = load_spec(path)
    except SpecError as exc:
        report("invalid spec", exc.messages)
        return 1
    report("warnings", validate_spec(data).warnings)
    target = output or default_output_path(path)
    try:
        write_document(target, render_spec(data, compute_layout(data)))
    except OSError as exc:
        sys.stderr.write("cannot write '%s': %s\n" % (target, exc.strerror or exc))
        return 1
    sys.stdout.write("%s\n" % target)
    return 0


def command_new(situation: str, out_dir: str, model: Optional[str], debug: bool) -> int:
    """Ask the model for a new walkthrough, then validate, write and render it."""
    if len(situation) > MAX_SITUATION:
        sys.stderr.write(
            "situation is %d characters; the limit is %d\n" % (len(situation), MAX_SITUATION)
        )
        return 2
    transcript: Optional[List[str]] = [] if debug else None
    chosen = model or llm.default_model()
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        sys.stderr.write("cannot use '%s': %s\n" % (out_dir, exc.strerror or exc))
        return 1
    try:
        draft = llm.generate_spec(situation, chosen, transcript=transcript)
        spec, result = settle(draft, chosen, transcript)
    except llm.LLMNotConfigured as exc:
        sys.stderr.write("%s\n" % exc)
        return 2
    except llm.LLMError as exc:
        save_debug(transcript or [], out_dir)
        sys.stderr.write("generation failed: %s\n" % exc)
        return 1
    save_debug(transcript or [], out_dir)
    if spec is None:
        report("the model could not produce a valid walkthrough", result.errors)
        return 1
    report("warnings", result.warnings)
    json_path = unique_path(os.path.join(out_dir, slugify(spec["title"]) + ".json"))
    try:
        page_path = write_spec_and_page(spec, json_path)
    except OSError as exc:
        sys.stderr.write("cannot write '%s': %s\n" % (json_path, exc.strerror or exc))
        return 1
    sys.stdout.write("%s\n%s\n" % (json_path, page_path))
    return 0


def backup_path(path: str) -> str:
    """Return an unused ``<name>.bak`` companion for a spec file."""
    return unique_path(path + ".bak")


def command_revise(
    instruction: str, path: str, in_place: bool, model: Optional[str], debug: bool
) -> int:
    """Ask the model to revise a spec, writing the result to a new file."""
    if len(instruction) > MAX_SITUATION:
        sys.stderr.write(
            "instruction is %d characters; the limit is %d\n" % (len(instruction), MAX_SITUATION)
        )
        return 2
    try:
        current = load_spec(path)
    except SpecError as exc:
        report("invalid spec", exc.messages)
        return 1
    folder = os.path.dirname(os.path.abspath(path))
    transcript: Optional[List[str]] = [] if debug else None
    chosen = model or llm.default_model()
    try:
        draft = llm.revise_spec(current, instruction, chosen, transcript=transcript)
        spec, result = settle(draft, chosen, transcript)
    except llm.LLMNotConfigured as exc:
        sys.stderr.write("%s\n" % exc)
        return 2
    except llm.LLMError as exc:
        save_debug(transcript or [], folder)
        sys.stderr.write("revision failed: %s\n" % exc)
        return 1
    save_debug(transcript or [], folder)
    if spec is None:
        report("the model could not produce a valid walkthrough", result.errors)
        return 1
    report("warnings", result.warnings)
    try:
        target = _revision_target(path, in_place)
        page_path = write_spec_and_page(spec, target)
    except OSError as exc:
        sys.stderr.write("cannot write next to '%s': %s\n" % (path, exc.strerror or exc))
        return 1
    sys.stdout.write("%s\n%s\n" % (target, page_path))
    return 0


def _revision_target(path: str, in_place: bool) -> str:
    """Pick where a revision lands, backing the original up when replacing it."""
    if not in_place:
        stem, extension = os.path.splitext(path)
        return unique_path(stem + ".revised" + extension)
    shutil.copy2(path, backup_path(path))
    return path
