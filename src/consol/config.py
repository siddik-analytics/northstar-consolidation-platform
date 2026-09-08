"""
Consolidation paths, layer identity and the conventions every consolidation step shares.

Nothing here reads data. It exists so that no step can invent its own idea of what a layer
is, which entity an entry is posted to, or how tight a tolerance has to be.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
REFERENCE = DATA / "reference"
STAGING = DATA / "10_staging"
WAREHOUSE = DATA / "20_warehouse"
FAULTS_DIR = DATA / "faults"
CONSOL_DIR = STAGING / "05_consolidated"
EXCEPTIONS = STAGING / "exceptions"

DUCKDB_PATH = WAREHOUSE / "northstar.duckdb"
MANIFEST = DATA / "phase04_manifest.json"
CONTROL_RESULTS = DATA / "phase04_control_results.csv"
RECONCILIATION = DATA / "phase04_reconciliation.csv"
FAULT_RESULTS = DATA / "phase04_fault_results.csv"

#: The five canonical consolidation layers (ADR-0003). There are exactly five and a row
#: carrying any other layer_id is rejected. Statutory is 1+2+3+5; management adds 4.
LAYER = {
    "REPORTED": 1,      # entity reported, from the frozen Phase 3 conformed layer
    "IC_ELIM": 2,       # intercompany eliminations
    "CONSOL_ADJ": 3,    # investment elimination, PPA, amortisation, NCI, unrealised profit
    "MGMT_ADJ": 4,      # management adjustments -- NEVER in the statutory result
    "FX_CTA": 5,        # the translation adjustment
}
LAYER_NAME = {v: k for k, v in LAYER.items()}
STATUTORY_LAYERS = (1, 2, 3, 5)
MANAGEMENT_LAYERS = (1, 2, 3, 4, 5)

#: Where each layer is posted. Every consolidation entry goes to a virtual entity so that an
#: entity's reported figures still agree with its own trial balance (ADR-0014). CTA is the
#: exception: it is an attribute of a specific foreign operation, and posting it to a virtual
#: entity would make "what is Halden's CTA?" unanswerable.
ELIM_ENTITY = {2: "ELIM-IC", 3: "ELIM-CON", 4: "ELIM-MGT"}

#: Equity accounts frozen at the rate of their originating transaction (FX-P03). A frozen
#: balance keeps that rate forever: share capital does not move because a spot rate moved.
HISTORICAL_EQUITY = ("310100", "310200", "315100")

#: Retained earnings. Opening is never retranslated (FX-P04); the year-end close carries the
#: sum of the year's translated months (FX-P05).
RETAINED_EARNINGS = ("320100", "320200")

#: The CTA roll-forward, held as three accounts so closing is derived and continuity is
#: testable (FX-P17, FX-P06, FX-P18, FX-P19).
CTA_OPENING, CTA_MOVEMENT, CTA_RECYCLED = "330100", "330200", "330300"

#: The five NCI accounts that make the roll-forward auditable rather than a moving balance.
NCI_OPENING, NCI_RESULT, NCI_DIVIDEND = "340100", "340200", "340300"
NCI_CTA, NCI_OWNERSHIP = "340400", "340500"
NCI_IN_PL = "850100"          # net income attributable to NCI, below tax

#: Consolidation-created accounts. None of these exists in any source ledger.
GOODWILL = "160100"
#: The approved group chart already carries the acquired intangible classes and their
#: accumulated amortisation. The engine posts to those rather than inventing accounts:
#: an account that exists in a journal and not in the chart is silently dropped by every
#: join, and the balance sheet stops balancing by exactly the amount nobody can see.
PPA_INTANGIBLES = ("165100", "165200")     # customer relationships, technology and patents
PPA_ACCUM_AMORT = "166100"
PPA_AMORT_EXPENSE = "720100"
PPA_DTL = "240100"
INVESTMENT = "178100"
PUP_INVENTORY = "130500"
#: The chart has no dedicated line for the unrealised-profit charge, so it is posted to the
#: inventory adjustment account, which is inside cost of sales where the design requires the
#: charge to sit. Recorded here rather than added to the approved chart.
PUP_COS = "530100"

#: The intercompany BALANCE relationship, as two sides rather than as account pairs.
#:
#: A balance is matched against its counterparty, not account by account, because the charts
#: do not agree on how many accounts it takes. Sable carries no separate group treasury
#: current account and no separate affiliate note: both are reported inside the ordinary
#: intercompany trade account (a documented Phase 3 substitution). Matching 120500 only
#: against 210500 would report every Sable entity's pool position as a missing counterpart
#: while Topco's side sat unmatched in 225100 -- two large exceptions that are the same real,
#: fully matched balance seen through two different charts.
#:
#: The elimination is still posted account by account, in proportion to what each account
#: actually holds, so the consolidated balance on every intercompany account is nil.
IC_BALANCE_HOLDER = ("120500", "125100", "175100")
IC_BALANCE_OWING = ("210500", "225100", "235100")
#: The intercompany FLOW relationship, as two sides, for the same reason as the balance one.
#: Kestrel books every kind of intercompany cost to one account under Materialaufwand -- a
#: documented Phase 3 substitution -- so a German buyer's service purchases arrive in the
#: product cost account. Matching category against category would report every one of those
#: as a missing counterpart on both sides at once. The pair's trading in a month is what has
#: to net; which accounts it netted across stays on the legs.
IC_FLOW_HOLDER = ("490100", "490200", "490300", "490400", "795100")
IC_FLOW_OWING = ("590100", "590200", "695100", "695200", "695300", "795200")

#: Tolerances. Structural identities are tested at the cent; derived comparisons against an
#: independently produced expectation carry the tolerance the policy states.
TOL_BALANCE_USD = 0.01          # a journal, a trial balance, a roll-forward
TOL_STATEMENT_USD = 0.01        # assets = liabilities + equity, and the cash flow tie
TOL_IC_RESIDUAL_USD = 1.00      # CTL-IC-01: an entity pair, after elimination
TOL_CTA_WARN = 0.005            # CTL-FX-04: 0.5% of the movement warns
TOL_CTA_BLOCK = 0.02            # 2% blocks
TOL_ANCHOR_PCT = 0.01           # a consolidated caption against its approved anchor
#: Cross-artefact reconciliation. Two artefacts expressing one measure are compared against the
#: authoritative fact, and every line on each side is already rounded to the cent, so a few
#: cents of accumulated presentation rounding is all that is allowed. It is a rounding
#: allowance and not room for a difference: each control reports the worst it measured.
TOL_XAR_USD = 0.05

#: Scenario and version coverage. Actual is consolidated in full; the planning scenarios
#: share the same grain and the same engine, with their own rate set.
SCENARIOS = {"ACT": "ACTUAL", "BUD": "BUDGET", "FC": "FORECAST"}


def ensure_dirs() -> None:
    for path in (CONSOL_DIR, EXCEPTIONS, WAREHOUSE):
        path.mkdir(parents=True, exist_ok=True)


_WRITE_ARTEFACTS = True


def set_artefact_writing(enabled: bool) -> None:
    """A fault run must never overwrite the clean baseline's artefacts."""
    global _WRITE_ARTEFACTS
    _WRITE_ARTEFACTS = enabled


def writing_artefacts() -> bool:
    return _WRITE_ARTEFACTS
