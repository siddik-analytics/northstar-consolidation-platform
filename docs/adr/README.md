# Architecture Decision Records

Each ADR records a decision where a reasonable practitioner could have chosen differently,
the alternatives considered, and the consequences accepted. Decisions with only one sensible
answer are documented in the design docs, not here.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-duckdb-as-consolidation-engine.md) | DuckDB as the consolidation and warehouse engine | Accepted |
| [0002](0002-unified-fact-across-scenarios.md) | One unified fact table across Actual, Budget and Forecast | Accepted |
| [0003](0003-consolidation-layer-model.md) | Consolidation layers instead of storing only consolidated results | Accepted, amended 1.1 |
| [0004](0004-prior-year-derived-not-stored.md) | Prior Year derived by date offset, not stored | Accepted |
| [0005](0005-fx-translation-method.md) | Monthly-average FX, closing-rate balance sheet, computed CTA | Accepted |
| [0006](0006-cash-flow-derived-indirect.md) | Cash flow derived from balance sheet movements | Accepted |
| [0007](0007-mapping-as-effective-dated-config.md) | COA mapping as effective-dated configuration, not code | Accepted |
| [0008](0008-revenue-detail-separate-fact.md) | Customer and product detail in a separate reconciled fact | Accepted |
| [0009](0009-ownership-and-consolidation-scope.md) | Full consolidation with one NCI; no equity-method investees | Accepted |
| [0010](0010-star-schema-and-pbip.md) | Star schema, flattened hierarchies, calculation groups, PBIP/TMDL | Accepted |
| [0011](0011-anchor-first-deterministic-modelling.md) | Anchor-first deterministic modelling | Accepted |
| [0012](0012-statistical-accounts-in-the-gl-fact.md) | Statistical accounts in the GL fact, outside the trial balance | Accepted |
| [0013](0013-adjusted-ebitda-definition.md) | Adjusted EBITDA definition and add-back policy | Accepted, amended 1.1 |
| [0014](0014-elimination-entities.md) | Eliminations posted to dedicated virtual entities | Accepted |
| [0015](0015-covenant-and-economic-leverage.md) | Two leverage measures, and a reserved Downside scenario | Accepted |
| [0016](0016-source-layer-measurement-reserve.md) | The source-layer difference is a disclosed equity reserve, never a plug | **Superseded by 0017** |
| [0017](0017-layer-1-equity-bridge-and-derived-cta.md) | The layer-1 equity bridge, and a CTA derived from source balances | Accepted |
| [0018](0018-revolver-utilisation-and-interest.md) | Revolver interest priced off a daily utilisation model | Accepted |
| [0019](0019-five-layer-ingestion-with-line-level-lineage.md) | Five ingestion layers, ERP-specific adapters, line-level lineage | Accepted |
| [0020](0020-mapping-rules-as-an-executable-configuration-language.md) | Mapping rules as an executable configuration language | Accepted |
| [0021](0021-source-findings-are-baselined-not-downgraded.md) | Three control states, and a source finding baselined at its population | Accepted |
| [0022](0022-money-is-decimal-and-artefacts-are-totally-ordered.md) | Money is DECIMAL; every committed artefact is written in a total order | Accepted |
| [0023](0023-intercompany-balances-are-built-pair-by-pair.md) | Intercompany balances built pair by pair; every posting names its counterparty | Accepted |
| [0024](0024-two-reconciled-consolidation-facts.md) | Two reconciled consolidation facts: a journal at leg grain and a fact at reporting grain | Accepted |
| [0025](0025-the-entity-ledger-supersedes-the-phase-1-nci-estimate.md) | The entity ledger supersedes the Phase 1 NCI earnings estimate | Accepted |
| [0026](0026-a-declared-key-is-a-contract.md) | A declared key is a contract, proved over its population, not a naming convention | Accepted |
| [0027](0027-a-derived-version-is-still-a-governed-version.md) | A derived version is still a governed version: PY_DERIVED belongs in the version master | Accepted |
| [0028](0028-lineage-ids-hash-content-artefact-digests-hash-bytes.md) | A lineage id hashes content; an artefact digest hashes bytes | Accepted |
