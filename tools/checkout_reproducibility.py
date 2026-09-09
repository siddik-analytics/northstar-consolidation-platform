"""
Prove the build ids survive a checkout.

    python tools/checkout_reproducibility.py

Defect P6-D-02 was found the hard way: a rebase re-checked-out several declared build inputs,
their line endings changed, and every downstream build id moved while not one byte of *content*
did. Proving the fix needs the same situation created on purpose.

Two controlled input trees are built from the committed content of every declared build input --
tree **A** written with LF throughout, tree **B** with CRLF -- and each phase's real `build_id`
is evaluated against both. The two must agree, for every phase.

This is the checkout simulation the environment cannot otherwise give: git will only produce
one form at a time on a given machine, so the other has to be constructed. What is compared is
the platform's own hashing code, not a re-implementation of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import lineage
from src.consol.run import BUILD_INPUTS as P4
from src.marts.run import BUILD_INPUTS as P5
from src.pipeline.run import BUILD_INPUTS as P3
from src.powerbi.run import BUILD_INPUTS as P6

PHASES = (("Phase 3", P3), ("Phase 4", P4), ("Phase 5", P5), ("Phase 6A", P6))
CRLF = "\r\n"


def materialise(inputs, root: Path, newline: str) -> list[Path]:
    """
    Write each declared input into `root` with the given line ending.

    The repository-relative path is preserved, because the build id hashes the input's name as
    well as its content -- writing everything flat would silently change the answer and prove
    nothing.
    """
    out = []
    for path in inputs:
        source = Path(path)
        text = source.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        try:
            relative = source.resolve().relative_to(ROOT)
        except ValueError:
            relative = Path(source.name)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.replace("\n", newline).encode("utf-8"))
        out.append(target)
    return out


def main(argv: list[str]) -> int:
    import tempfile

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        a, b = tmp / "checkout_lf", tmp / "checkout_crlf"

        print(f"{'phase':10}{'LF checkout':>20}{'CRLF checkout':>20}  verdict")
        print("-" * 62)
        for name, inputs in PHASES:
            # The real hashing code, evaluated against each tree. `lineage.build_id` is what
            # every phase's `build_id()` calls, so this is not a re-implementation.
            lf_files = materialise(inputs, a, "\n")
            crlf_files = materialise(inputs, b, CRLF)

            # Hash relative to each tree root, so the recorded names match.
            import src.lineage.digest as digest
            original_root = digest.ROOT
            try:
                digest.ROOT = a
                lf_id = lineage.build_id(lf_files)
                digest.ROOT = b
                crlf_id = lineage.build_id(crlf_files)
            finally:
                digest.ROOT = original_root

            ok = lf_id == crlf_id
            failures += 0 if ok else 1
            print(f"{name:10}{lf_id:>20}{crlf_id:>20}  {'MATCH' if ok else 'DIFFER'}")

    print("-" * 62)
    print("BUILD IDS SURVIVE A CHECKOUT" if not failures
          else f"{failures} phase(s) still checkout-dependent")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
