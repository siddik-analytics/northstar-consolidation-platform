# Phase 7 — Portfolio release and presentation

**Status:** package complete — **awaiting owner publication approval**; nothing tagged or
published
**Baseline:** Phase 6B.1 accepted at `3ed985a`; Excel and Power BI frozen in this phase
**Docs:** [README](../../README.md) · [case study](../portfolio/case-study.md) ·
[copy](../portfolio/copy.md) · [video script](../portfolio/video-script.md) ·
[assets](../assets/portfolio/MANIFEST.md)

---

## 1. The final baselines

| artefact | digest / id | how it was frozen |
|---|---|---|
| Excel workbook | **`0576e03d47570d2c`** | one governance-only refresh approved by the owner: `tools/workbook_diff.py` against the previous frozen file shows exactly four numeric cells (the Phase 5.1 control count 295 → 304 on the Cover and sheet 13), 0 text, 0 financial; 17/17 reconciliations, 0 layout findings, calculated and rendered by Excel. **Permanent: the workbook is not regenerated for later control counts.** |
| Power BI definition digest | **`6230f1c9a8f4246b`** | the sealed Phase 6B.1 model |
| Power BI report build id | **`82890711b04f655a`** | the report declarations |
| Power BI project digest | **`f8778db9cf7f608c`** | the generated project on disk, equal in all three manifests |
| commit | `69a1c89` (baselines) → the Phase 7 commit | |

The Power BI baseline was verified natively once more before freezing: the PBIP opened
through Desktop's own dialog and refreshed; ten pages rendered with zero visual errors;
navigation 10/10; the unit slicer narrows (Revenue 279.0 → 84.1) and clears; the Actual
line ends at the close; variance % reads (32.8%) for EBIT; the covenant tile reads
*Indicative* at the close and *Compliant* at the test dates; the hierarchy sorts at caption
grain; the year-to-date bridge sums to statutory EBITDA; the ten rendered cards equal the
engine (`P6B-20…25`, `P6B1-HS/SC/BR`, all passing).

## 2. What this phase produced

| deliverable | where |
|---|---|
| README rebuilt as a project landing page | `README.md` |
| case study | `docs/portfolio/case-study.md` |
| GitHub description and topics, Upwork entry, resume bullets, LinkedIn Featured copy | `docs/portfolio/copy.md` |
| hero composition | `docs/assets/portfolio/hero.png` |
| architecture diagram | `docs/assets/portfolio/architecture/architecture.png` |
| framed Excel screenshots (5) and Power BI screenshots (8) | `docs/assets/portfolio/excel/`, `docs/assets/portfolio/powerbi/` |
| walkthrough video, 2:30, and the 70-second silent preview | `docs/assets/portfolio/video/` |
| voice-over script and cue sheet | `docs/portfolio/video-script.md` |
| asset builders (reproducible from the renders and captures) | `tools/portfolio_assets.py`, `tools/portfolio_video.py` |

Selected for the README, in order: hero · Excel Executive summary · Excel Consolidation &
controls · Power BI Executive Overview · Power BI Debt & Covenants · Power BI Consolidation &
Controls · Power BI Cash Flow & Liquidity · the preview. The P&L, business-unit, EBITDA
bridge and cash-flow workbook sheets are framed and available but not placed, to keep the
page paced.

## 3. File hygiene

* `docs/assets/phase-06b/wip/` renamed `stop-331814d/`: the renders at the Phase 6B stop
  are evidence for three closed defects and stay, labelled as what they are.
* No local path in any committed file (the video producer's frame directory is the system
  temp directory); no personal machine information; QA scratch renders live outside the
  repository; the workbook renders under `data/90_exports/` are already ignored.
* Phase evidence folders (`phase-05-2a`, `phase-06a-2`, `phase-06a-3`, `phase-06b`,
  `phase-06b-1`) are kept: each is referenced from a phase report or the defect register.
* Committed size added by this phase: ~13 MB, of which the video is 9.7 MB.

## 4. Regression

Run after the baselines were frozen and the portfolio material written; nothing in the
finance outputs moved (the Excel digest and the three Power BI digests above are the ones the
regression reproduces).

## 5. Release recommendation

`v1.0` — the first public release: every phase complete, both reporting artefacts frozen,
the control suite clean, no open defect. Annotated tag, created only on the owner's approval.

## 6. Owner review checklist

1. README renders on GitHub: hero, architecture, seven screenshots and the preview load;
   the section order reads as a landing page, not a manual.
2. The hero communicates a finance platform rather than spreadsheets.
3. Screenshots: Excel from the final workbook renders, Power BI from the final native
   captures; framing consistent; no cropped labels; values as the artefacts show them.
4. Case study reads as a consulting case study and states the environment is synthetic.
5. Copy: GitHub description within the limit, topics valid, Upwork entry discloses the
   synthetic environment, resume bullets and LinkedIn copy make no unsupported outcome claim.
6. Video: 2:30, cuts and holds long enough to read, captions accurate, no audio; the script
   matches the cues.
7. Control story: the counts (677 controls, 83 fixtures, 588 tests) match the registers.
8. AI disclosure: present, concise, positioned as assisted development under governed
   review.
9. No stale phase status, no local path, no debug language in the public-facing pages.
10. Approve the tag `v1.0` and the repository description and topics.
