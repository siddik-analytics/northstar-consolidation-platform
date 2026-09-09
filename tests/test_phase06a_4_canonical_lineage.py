"""
P6-D-02 — build ids that depended on how a file had been checked out.

The symptom: rebasing the Phase 6A branch moved every downstream build id while not one byte
of *content* changed. The cause: `build_id()` hashed raw bytes, and git rewrites line endings.
The form that reproduced each committed id turned out to be a per-file mixture of CRLF and LF,
which is the defect stated plainly — the ids identified which files had last been authored on
Windows, not what the inputs said.

The correction is one shared canonical hasher (`src/lineage/digest.py`). These tests hold both
halves of it: that a line ending no longer changes a lineage id, and that **everything else
still does**. A hash that stops noticing real differences is a worse defect than the one it
replaced, so most of what follows is about what must still change the answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import lineage
from src.lineage.digest import UnknownFileType

CRLF = "\r\n"

SAMPLE = ("group_account,account_name,is_ebitda\n"
          "400100,Product revenue,true\n"
          "500100,Cost of sales,true\n"
          "\n"
          "610100,Sponsor fee  ,false\n")


def _write(directory: Path, name: str, text: str, newline: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


# ===================================================================== line endings
def test_lf_crlf_and_cr_produce_one_build_id(tmp_path):
    """The defect itself: three encodings of identical content, one lineage id."""
    lf = _write(tmp_path / "lf", "a.csv", SAMPLE, "\n")
    crlf = _write(tmp_path / "crlf", "a.csv", SAMPLE, CRLF)
    cr = _write(tmp_path / "cr", "a.csv", SAMPLE, "\r")

    ids = {lineage.build_id([p]) for p in (lf, crlf, cr)}
    assert len(ids) == 1, f"line endings still change the build id: {ids}"


def test_line_endings_change_the_exact_digest(tmp_path):
    """
    And the byte digest must still notice, because it answers a different question.

    Redefining the byte-level digest as a semantic one would destroy the ability to prove a
    rebuild produced an identical file.
    """
    lf = _write(tmp_path / "lf", "a.csv", SAMPLE, "\n")
    crlf = _write(tmp_path / "crlf", "a.csv", SAMPLE, CRLF)
    assert lineage.exact_digest(lf) != lineage.exact_digest(crlf)


def test_a_byte_order_mark_does_not_change_the_build_id(tmp_path):
    plain = tmp_path / "plain.csv"
    plain.write_bytes(SAMPLE.encode("utf-8"))
    with_bom = tmp_path / "bom.csv"
    with_bom.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
    # different names, so compare content hashes directly
    assert lineage.canonical_bytes(plain) == lineage.canonical_bytes(with_bom)


# ===================================================================== what must still change it
def test_changed_text_content_changes_the_build_id(tmp_path):
    a = _write(tmp_path / "a", "x.csv", SAMPLE, "\n")
    b = _write(tmp_path / "b", "x.csv", SAMPLE.replace("Product revenue", "Service revenue"),
               "\n")
    assert lineage.build_id([a]) != lineage.build_id([b])


def test_a_changed_number_changes_the_build_id(tmp_path):
    a = _write(tmp_path / "a", "x.csv", SAMPLE, "\n")
    b = _write(tmp_path / "b", "x.csv", SAMPLE.replace("400100", "400200"), "\n")
    assert lineage.build_id([a]) != lineage.build_id([b])


def test_a_trailing_space_changes_the_build_id(tmp_path):
    """
    Whitespace is NOT normalised, and that is deliberate.

    A trailing space inside a quoted CSV field is data and indentation in Python is syntax.
    Folding them would make the hash agree about files that genuinely differ, which is a worse
    failure than the one being corrected.
    """
    a = _write(tmp_path / "a", "x.csv", SAMPLE, "\n")
    b = _write(tmp_path / "b", "x.csv", SAMPLE.replace("Sponsor fee  ", "Sponsor fee"), "\n")
    assert lineage.build_id([a]) != lineage.build_id([b])


def test_a_removed_blank_line_changes_the_build_id(tmp_path):
    a = _write(tmp_path / "a", "x.csv", SAMPLE, "\n")
    b = _write(tmp_path / "b", "x.csv", SAMPLE.replace("true\n\n610100", "true\n610100"), "\n")
    assert lineage.build_id([a]) != lineage.build_id([b])


def test_changed_indentation_changes_the_build_id(tmp_path):
    a = _write(tmp_path / "a", "m.py", "def f():\n    return 1\n", "\n")
    b = _write(tmp_path / "b", "m.py", "def f():\n        return 1\n", "\n")
    assert lineage.build_id([a]) != lineage.build_id([b])


def test_a_renamed_input_changes_the_build_id(tmp_path):
    a = _write(tmp_path, "one.csv", SAMPLE, "\n")
    b = _write(tmp_path, "two.csv", SAMPLE, "\n")
    assert lineage.build_id([a]) != lineage.build_id([b])


def test_reordered_inputs_change_the_build_id(tmp_path):
    a = _write(tmp_path, "a.csv", SAMPLE, "\n")
    b = _write(tmp_path, "b.csv", "x,y\n1,2\n", "\n")
    assert lineage.build_id([a, b]) != lineage.build_id([b, a])


def test_content_shifting_across_a_file_boundary_changes_the_build_id(tmp_path):
    """Length-prefixing each input rules out the classic concatenation collision."""
    a1 = _write(tmp_path / "one", "a.csv", "ab\n", "\n")
    b1 = _write(tmp_path / "one", "b.csv", "c\n", "\n")
    a2 = _write(tmp_path / "two", "a.csv", "a\n", "\n")
    b2 = _write(tmp_path / "two", "b.csv", "bc\n", "\n")
    assert lineage.build_id([a1, b1]) != lineage.build_id([a2, b2])


# ===================================================================== binary
def test_binary_files_are_not_canonicalised(tmp_path):
    path = tmp_path / "x.parquet"
    payload = b"PAR1\r\n\x00\r\x01binary\r\npayload"
    path.write_bytes(payload)
    assert lineage.canonical_bytes(path) == payload, "a binary file must not be text-folded"


def test_a_binary_byte_change_changes_both_digests(tmp_path):
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    a.write_bytes(b"PAR1\x00\x01\x02")
    b.write_bytes(b"PAR1\x00\x01\x03")
    assert lineage.exact_digest(a) != lineage.exact_digest(b)
    assert lineage.canonical_bytes(a) != lineage.canonical_bytes(b)


def test_an_undeclared_file_type_fails_loudly(tmp_path):
    """Sniffing would reintroduce exactly the environment-dependent behaviour being removed."""
    path = tmp_path / "mystery.dat"
    path.write_bytes(b"anything")
    with pytest.raises(UnknownFileType):
        lineage.canonical_bytes(path)


def test_text_and_binary_suffix_sets_do_not_overlap():
    assert not (lineage.TEXT_SUFFIXES & lineage.BINARY_SUFFIXES)


# ===================================================================== the platform itself
def test_every_declared_build_input_has_a_declared_file_type():
    from src.consol.run import BUILD_INPUTS as P4
    from src.marts.run import BUILD_INPUTS as P5
    from src.pipeline.run import BUILD_INPUTS as P3
    from src.powerbi.run import BUILD_INPUTS as P6

    for group in (P3, P4, P5, P6):
        for path in group:
            lineage.is_text(Path(path))          # raises if undeclared


def test_no_phase_bypasses_the_shared_hasher():
    """
    Four subtly different implementations was the shape of the original defect.

    Read as source: a phase that hashes `path.read_bytes()` inside its own `build_id` is not
    using the canonical hasher, whatever it says it does.
    """
    for module in ("src/pipeline/run.py", "src/consol/run.py", "src/marts/run.py",
                   "src/powerbi/run.py"):
        source = (ROOT / module).read_text(encoding="utf-8")
        start = source.index("def build_id(")
        body = source[start:source.index("\ndef ", start + 1)]
        assert "lineage.build_id" in body, f"{module} does not use the shared hasher"
        assert "read_bytes" not in body, f"{module} still hashes raw bytes"


def test_the_committed_manifests_reproduce_their_canonical_ids():
    from src.consol.run import build_id as p4
    from src.marts.run import build_id as p5
    from src.pipeline.run import build_id as p3
    from src.powerbi.run import build_id as p6

    for name, fn in (("phase03", p3), ("phase04", p4), ("phase05", p5), ("phase06a", p6)):
        manifest = json.loads((ROOT / "data" / f"{name}_manifest.json").read_text())
        assert manifest["build_id"] == fn(), f"{name} does not reproduce its build id"


def test_the_whole_repository_reproduces_across_line_endings(tmp_path):
    """
    The end-to-end proof: every declared input, in two checkouts, one set of ids.

    This is the checkout simulation in miniature -- the same content written once with LF and
    once with CRLF, hashed through the real phase functions.
    """
    from src.consol.run import BUILD_INPUTS as P4
    from src.marts.run import BUILD_INPUTS as P5
    from src.pipeline.run import BUILD_INPUTS as P3
    from src.powerbi.run import BUILD_INPUTS as P6

    for group in (P3, P4, P5, P6):
        lf_ids, crlf_ids = [], []
        for path in group:
            raw = Path(path).read_bytes()
            text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            lf = tmp_path / "lf" / Path(path).name
            crlf = tmp_path / "crlf" / Path(path).name
            lf.parent.mkdir(parents=True, exist_ok=True)
            crlf.parent.mkdir(parents=True, exist_ok=True)
            lf.write_bytes(text.encode("utf-8"))
            crlf.write_bytes(text.replace("\n", CRLF).encode("utf-8"))
            lf_ids.append(lf)
            crlf_ids.append(crlf)
        assert lineage.build_id(lf_ids) == lineage.build_id(crlf_ids)
