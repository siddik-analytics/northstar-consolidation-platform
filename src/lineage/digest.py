"""
Canonical content hashing.

Two different questions get asked of a file in this platform, and they have always needed two
different answers:

**"Is this the same input?"** — a build id. It identifies the *content that went in*, and it
must survive a checkout. Git rewrites line endings; a line ending carries no meaning; a build
id that changes when a file is checked out on a different platform is reporting drift that did
not happen. This is what `build_id()` answers.

**"Is this the same file, byte for byte?"** — an artefact digest. It proves a rebuild produced
an identical file, and for that question a single byte matters absolutely. This is what
`exact_digest()` answers, and it must never be quietly turned into the first kind.

Defect **P6-D-02** was the first question being answered with the second question's method.
Rebasing the Phase 6A branch re-checked-out several declared build inputs, their line endings
changed, and every downstream build id moved while not one byte of *content* differed. The form
that reproduced each committed id turned out to be a per-file mixture of CRLF and LF — proof
that the ids depended on which files had last been authored on Windows rather than on what the
inputs said.

## What canonicalisation does, and what it deliberately does not

For a text input: decode as UTF-8, drop a leading byte-order mark, fold `\\r\\n` and a bare
`\\r` to `\\n`, re-encode as UTF-8. That is all.

It does **not** trim trailing spaces, collapse runs of whitespace, drop blank lines or strip
indentation. Those carry meaning — a trailing space inside a quoted CSV field is data, and
indentation in Python is syntax. Normalising them would make the hash agree about files that
genuinely differ, which is a worse failure than the one being fixed.

For a binary input: the raw bytes, untouched.

A file whose type is not declared raises `UnknownFileType`. Guessing whether something is text
by sniffing it would reintroduce exactly the class of silent, environment-dependent behaviour
this module exists to remove.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Text: canonicalised before hashing. Line endings in these files are an artefact of whichever
#: platform last wrote them and say nothing about the content.
TEXT_SUFFIXES = frozenset({
    ".csv", ".json", ".md", ".py", ".sql", ".tmdl", ".txt", ".yml", ".yaml",
    ".pbip", ".pbism", ".pbir", ".cfg", ".ini", ".toml",
})

#: Binary: hashed byte for byte. Canonicalising these would corrupt them, and their whole
#: purpose is to prove byte identity.
BINARY_SUFFIXES = frozenset({
    ".parquet", ".xlsx", ".xlsb", ".xls", ".pbix", ".png", ".jpg", ".jpeg", ".pdf",
    ".zip", ".duckdb", ".gz", ".woff", ".woff2", ".ico",
})


class UnknownFileType(ValueError):
    """A file whose text/binary status is not declared. Never guessed."""


def is_text(path: Path) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return True
    if suffix in BINARY_SUFFIXES:
        return False
    raise UnknownFileType(
        f"{Path(path).name}: suffix {suffix!r} is in neither TEXT_SUFFIXES nor "
        f"BINARY_SUFFIXES. Declare it in src/lineage/digest.py rather than letting the "
        f"hasher guess -- guessing is how a build id becomes environment-dependent.")


def canonical_bytes(path: Path | str) -> bytes:
    """
    The bytes that represent this file's *content*, independent of how it was checked out.

    Text is decoded as UTF-8 (tolerating a BOM), line endings are folded to `\\n`, and the
    result is re-encoded as UTF-8. Binary is returned untouched.
    """
    path = Path(path)
    raw = path.read_bytes()
    if not is_text(path):
        return raw
    # utf-8-sig drops a BOM if there is one and behaves as plain utf-8 if there is not.
    text = raw.decode("utf-8-sig")
    # CRLF first, so a CRLF does not become two newlines via the bare-CR rule.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8")


def _relative(path: Path) -> str:
    """The repository-relative path, so a digest does not depend on where the repo lives."""
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def build_id(paths, length: int = 16) -> str:
    """
    A lineage identifier for a set of declared inputs: their names and their canonical content.

    The name of each input is hashed alongside its content. Concatenating content alone leaves
    the boundary between two files ambiguous -- content shifting across it would produce the
    same digest -- and it would not notice an input being renamed or the declared order
    changing. Both are cheap to rule out and worth ruling out.
    """
    h = hashlib.sha256()
    for path in paths:
        p = Path(path)
        content = canonical_bytes(p)
        h.update(_relative(p).encode("utf-8"))
        h.update(b"\0")
        h.update(str(len(content)).encode("ascii"))
        h.update(b"\0")
        h.update(content)
    return h.hexdigest()[:length]


def exact_digest(path: Path | str) -> str:
    """
    A byte-for-byte digest of a produced artefact. Never canonicalised.

    This answers a different question from `build_id`: not "is this the same input" but "did
    the rebuild produce an identical file". A single byte matters, including a line ending,
    because a published artefact is written by this platform rather than checked out by git.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
