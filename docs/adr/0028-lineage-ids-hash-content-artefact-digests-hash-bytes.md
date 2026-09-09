# ADR-0028 — a lineage id hashes content; an artefact digest hashes bytes

**Status:** accepted, Phase 6A.1
**Amends:** [ADR-0022](0022-money-is-decimal-and-artefacts-are-totally-ordered.md) — the
determinism decision stands; this settles what a build id is a digest *of*
**Related:** defect P6-D-02

## Context

Every phase computed its build id the same way:

```python
def build_id() -> str:
    h = hashlib.sha256()
    for path in BUILD_INPUTS:
        h.update(path.read_bytes())          # raw bytes
    return h.hexdigest()[:16]
```

Rebasing the Phase 6A branch re-checked-out several declared inputs. Git rewrites line endings
on checkout, so their bytes changed. Not one byte of *content* changed — and every downstream
build id moved.

The diagnosis was more uncomfortable than the symptom. The form that reproduced each committed
id turned out to be a **per-file mixture**:

```
phase03 reproduces with  build_digest.txt=CRLF, mapping_rules.csv=CRLF, group_coa.csv=CRLF,
                         source_coa_aurora.csv=CRLF, source_coa_sable.csv=CRLF,
                         source_coa_kestrel.csv=LF, entity_master.csv=LF
```

The ids were not identifying the inputs. They were identifying **which files had last been
authored on Windows**. A fresh clone on any platform would have produced different lineage
identifiers for an identical repository, and `docs/reproducibility.md` claimed otherwise.

## Decision

**Two questions, two answers, and they are not interchangeable.**

| | question | method |
|---|---|---|
| **Lineage / build id** | *is this the same input?* | canonical text hashing |
| **Exact artefact digest** | *is this the same file, byte for byte?* | raw bytes |

One shared implementation, `src/lineage/digest.py`, and every phase calls it.

### Canonicalisation, and its limits

For a text input: decode UTF-8, drop a leading byte-order mark, fold `\r\n` and a bare `\r` to
`\n`, re-encode UTF-8.

**That is all it does.** It does not trim trailing spaces, collapse whitespace runs, drop blank
lines or strip indentation. A trailing space inside a quoted CSV field is data; indentation in
Python is syntax. Normalising those would make the hash agree about files that genuinely
differ — a worse failure than the one being fixed, and a silent one.

### Text and binary are declared, never sniffed

`TEXT_SUFFIXES` and `BINARY_SUFFIXES` are explicit lists. A file whose suffix is in neither
raises `UnknownFileType`. Guessing by inspecting content would reintroduce exactly the class of
silent, environment-dependent behaviour this ADR removes: the same file could be treated one
way on one machine and another way elsewhere.

### The build id hashes names as well as content

Each input contributes its repository-relative path, its length, and its canonical bytes.
Concatenating content alone leaves the boundary between two files ambiguous — content shifting
across it produces the same digest — and it notices neither a renamed input nor a change in the
declared order. Both are cheap to rule out.

### What deliberately did **not** change

`exact_digest()` — every published Parquet, and the Excel workbook — still hashes raw bytes.
Those files are written by this platform moments before they are hashed and are never checked
out in between, so byte identity is both achievable and the stronger claim: it proves two runs
produced the same *bytes*, not merely the same content. The source dataset digest
(`src/generation/build.py`) is the same case and is left alone for the same reason.

## Consequences

The build ids rebaseline. They cascade, because each phase's manifest is an input to the next:

| | before | after |
|---|---|---|
| source layer digest | `8013298c…` | `8013298c…` **unchanged** |
| Phase 3 | `6e0c519360d3669b` | `468dbf847805d6c9` |
| Phase 4 | `fcfa135a222f58ba` | `cc89cf0317801b36` |
| Phase 5 | `50d85b385b7a2a41` | `00d3dd24020f900d` |
| workbook | `0a26d3980bd463e5` | `e8b97d9e780a13a7` |
| Phase 6A | `458ca84c1903b9f0` | `fc2823eb5a85b42c` |
| Phase 6A project | `c04c498f4469329c` | `47103ccc440668f4` |

**Metadata only.** 325,352 rows compared across eighteen grains at a maximum absolute
difference of `0.00`; the workbook shows **zero** numeric differences across 615,270 valued
cells, its only change being the two lineage stamps it prints on the cover; the semantic
model's definition digest is identical, and its 49 controls and 10 fixtures are unchanged.

Five permanent controls (`P7-RPR-01` … `P7-RPR-05`) and a fault fixture (`F7-RPR-01`) run with
the rest of the suite, because a unit test would not catch the *next* phase quietly writing its
own hasher. `P7-RPR-02` reads the source of every phase's `build_id` and fails if it hashes raw
bytes.

`tools/checkout_reproducibility.py` builds two controlled input trees — one LF, one CRLF — and
evaluates each phase's real `build_id` against both. All four agree, and all four agree with the
committed manifests.

## The thing worth remembering

A digest is only as meaningful as the question it answers, and the two questions here look
identical until one of them gives the wrong answer. "Are these the same inputs" and "is this the
same file" differ by exactly the things that carry no meaning — and a platform that conflates
them will eventually report drift that did not happen, which is how a reproducibility claim
quietly stops being worth anything.
