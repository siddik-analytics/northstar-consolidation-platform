# Phase 6A.2 — native PBIP compatibility

**Status:** sealed, awaiting owner review before Phase 6B resumes
**Baseline:** `0ec7824` (Phase 6B stop, P6B-D-01 / P6B-D-02 registered) on the approved Phase 6A
model; Excel frozen at `f29cd29`
**Docs:** [semantic model](../powerbi-semantic-model.md) · [controls](../powerbi-controls.md) ·
[defect register](../defect-register.md) · [reproducibility](../reproducibility.md) ·
[lessons §15](../architecture-lessons.md)

---

## 1. What this phase is

Phase 6A validated the semantic model by deploying it over TMSL to the Analysis Services
engine behind Power BI Desktop and executing its DAX there. Every control passed. Its report
also said, accurately, that the `.pbip` had not been opened in Desktop's UI, because `.pbip`
has no file association here and the Store build ignores a command-line argument.

Phase 6B needed pages rendered, so it found the native route — Desktop's own File > Open
dialog, driven through UI Automation — and the project did not open. Twice.

| defect | Desktop said | why the engine never saw it |
|---|---|---|
| **P6B-D-01** | *Property 'description' is unknown and is not expected in the situation it appears.* | the emitter wrote each inactive relationship's rationale as a `///` doc comment; TMDL maps `///` to `Description`, and a relationship has none. TMSL carries no comments |
| **P6B-D-02** | *Unsupported Table name "Measures" has been found in data model schema.* | the measures host was named `Measures`, which Desktop reserves. A fresh engine accepts it over TMSL |

Phase 6B stopped, as its brief required. This phase closes both at the emitter, adds the
control surface that was missing, and reseals.

## 2. The corrections

**P6B-D-01.** `src/powerbi/model.py` no longer writes `///` above a relationship. The rationale
is emitted as an annotation on the relationship, `Northstar_Rationale`, in the TMDL and — so
the two forms carry the same metadata — in the TMSL. The prose is byte-for-byte the text in
`config.INACTIVE_RELATIONSHIPS`, collapsed to one line because an annotation value is one
line. After a native open, `$SYSTEM.TMSCHEMA_ANNOTATIONS` in Desktop's own session database
returns all five. Nothing was stripped after generation; the generator emits valid TMDL.

**P6B-D-02.** `config.MEASURES_TABLE = "Northstar Measures"` is the one place the name lives;
the TMDL emitter, the TMSL emitter, the controls and the tests read it. Measures are
referenced as `[Measure]`, never table-qualified, so no DAX changed — verified rather than
assumed: the 89 measure definitions in the regenerated TMDL are identical to the sealed ones,
and every one evaluates in both the engine and Desktop's session. The table keeps its lineage
tag: the same object, renamed.

**Auto date/time.** Found by `P6-PBIP-04`: Desktop's session held 33 tables and 40
relationships against 28 and 36 declared, because Desktop's auto date/time adds a hidden
`LocalDateTable_*` per date column. The model has a governed Date dimension, so the project
now declares `__PBI_TimeIntelligenceEnabled = 0` at model level (TMDL and TMSL). What Desktop
loads is now exactly what the project declares.

`config.RESERVED_TABLE_NAMES` holds `{"measures"}` — the list Desktop has actually refused, not
a guess at one.

## 3. Native validation — what was actually done

`src/powerbi/desktop.py` is new and permanent. It:

1. waits until the machine has been idle for fifteen seconds (it takes the keyboard);
2. presses Ctrl+O in Desktop, types the project path into the Open dialog and submits it;
3. tracks the Desktop process that receives the file — a blank window loads in place, a
   window with a document loaded hands the file to a new process — and reads back either the
   loaded project's title or the text of the refusal dialog;
4. runs Home > Refresh > *Schema and data* through the ribbon and waits for Desktop's *"some of
   the tables have incomplete or no data"* and *"calculated objects need to be manually
   refreshed"* bars to clear;
5. counts tables, measures and relationships in the session database Desktop created for the
   project, addressed by the `msmdsrv` that is that Desktop's child;
6. captures the window with `PrintWindow` on its own handle — never a screen grab — and closes
   any instance it spawned.

**Result on Desktop 2.157.1354.0 (Store build):** the regenerated project opens in ~19 s,
refreshes every partition natively, and Desktop's session holds **28 tables, 89 measures, 36
relationships, 31 active** — equal to the project text and to the TMSL-deployed engine.
Evidence: `docs/assets/phase-06a-2/desktop_native_open_refreshed.png` (the control's own
capture) beside `desktop_P6B-D-02_unsupported_table_name.png` (the refusal that started this).

## 4. Dual validation — two surfaces, stated separately

| surface | proves | cannot prove | held by |
|---|---|---|---|
| **native project** — Desktop parses and loads the `.pbip` | the text on disk is a project Desktop accepts; the schema has no reserved names; the partitions load through Desktop's Power Query | that a measure is *right* | `P6-PBIP-01…04` |
| **engine** — TMSL deployment, refresh, real DAX | every measure parses and evaluates; the values reconcile to the marts and to Excel | that Desktop will open the file | `P6-SEM`, `P6-XAR`, `P6-XLS`, `P6-POL` |

They are not interchangeable, and the engine's answer is not even stable: **a fresh engine
accepts a table named `Measures` over TMSL, and the same engine refuses it once Desktop has
loaded a project into it** (*"The name of the object 'Table' cannot be the reserved string
'Measures'"*). Phase 6A deployed to a fresh engine, which is why P6B-D-02 passed 49 controls.
The project control does not depend on engine state.

## 5. Invariance

**Definitions.** A third digest was added, `definition_digest`: canonical JSON of every measure
(name, DAX, format, folder, description), every table specification, every relationship and
its rationale, the period-basis rows and the reporting close — and nothing about containers,
lineage tags, annotations or file layout.

| digest | Phase 6A.1 (sealed) | Phase 6A.2 | moved because |
|---|---|---|---|
| `definition_digest` | `c7f74db69a967dd9` | `c7f74db69a967dd9` | — (unchanged, as it must be) |
| `project_digest` | `47103ccc440668f4` | `9db029ca825664ae` | rationale as annotation; measures host renamed; auto date/time declared off |
| `build_id` | `fc2823eb5a85b42c` | `92d8040957b6a34f` | `config.py` and `model.py` are declared build inputs and both changed |

The generated project diff is exactly the three intended changes: `Measures.tmdl` →
`Northstar Measures.tmdl` (git detects the rename; 4 lines differ, all the name), 15 `///`
lines replaced by 5 annotation lines in `relationships.tmdl`, and one annotation plus two
renamed references in `model.tmdl`. The 89 measure definitions are byte-identical.

**Structure.** 28 tables (14 dimensions, 12 facts, Period Basis, the measures host), 89
measures, 31 active and 5 inactive relationships, cardinalities and directions unchanged —
counted in the project text, in the engine, and in Desktop's session.

**Values.** Every `P6-XAR` and `P6-XLS` control reports the same difference it reported in the
sealed Phase 6A.1 register — most exactly zero; leverage and the Excel ratios within the same
sub-tolerance rounding as before. Revenue 278,980,889.78; Gross Profit 75,980,813.59;
Statutory EBITDA 28,100,907.83; EBIT 15,473,409.60; Net Income (939,022.82); Total Assets
465,523,771.19; Closing Cash 14,579,689.06 — the Phase 6A table, reproduced on the resealed
model and, for the first time, also in Desktop's natively loaded session.

**Excel.** The approved design is untouched; the workbook was regenerated under the freeze's
one stated exception, because a regression explicitly required it. The workbook's control-status
tables (Cover and sheet 13) read the Phase 6A register, which now says 53/53; a frozen file
saying 49/49 contradicted the register, and `test_the_workbook_build_is_reproducible` failed
against it. `tools/workbook_diff.py` frozen (`016df00814dc5025`) → rebuilt
(`bde5ead1fbd6f945`): **4 numeric cells changed, all of them that control count; 0 text
differences; 0 cells added or removed; 0 financial values.** 17/17 reconciliations, 0 layout
findings, styling identical. Reverting is one command
(`git checkout f29cd29 -- data/90_exports/Northstar_Consolidation_Management_Reporting.xlsx
data/phase05_workbook_manifest.json`) if the owner prefers the stale count to a changed digest.

## 6. Controls and fixtures

| | before | after |
|---|---|---|
| controls | 49 in 4 families | **53 in 5 families**, 53 pass, 0 not executed |
| fixtures | 10 | **12**, 12 detected by their intended control |

`P6-PBIP-01` doc comments only where a Description exists · `P6-PBIP-02` no reserved table
name · `P6-PBIP-03` **Desktop opens and loads the project** (blocking; NOT_EXECUTED with the
reason when Desktop or an idle machine is unavailable) · `P6-PBIP-04` project text, engine and
Desktop session agree on counts.

`F6-PBIP-01` re-emits the `///` form and `F6-PBIP-02` puts the reserved name back; each
regenerates the project into a disposable directory, deploys it over TMSL, runs the controls,
and asks Desktop. Both are caught by the control named for them; the harness records what the
engine did alongside, because that line is the lesson.

## 7. Regression

Recorded in the final response and in the commit: the full pytest suite, every prior phase's
controls, the Excel reconciliations, and the semantic suite above.

## 8. Limitations

1. `P6-PBIP-03` needs Power BI Desktop installed and a machine nobody is typing on. Elsewhere it
   reports `NOT_EXECUTED` with the reason, and the phase run is not clean until it has run.
2. The reserved-name list is empirical — one entry, confirmed. Another reserved name would be
   found the same way this one was: by `P6-PBIP-03`, which is why it is blocking.
3. UI Automation is a workaround for a Store build that ignores its command line. It is honest
   — it uses the same parser a double-click would — and it is slower and more fragile than a
   command line would be.

Phase 6B has not resumed.
