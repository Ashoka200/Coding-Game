# Real Estate Investment Advisor — Build Plan (India, land-focused)

A second advisor bot: monitors public government activity across Indian states,
identifies growth corridors early (the "Hyderabad lesson" formalized), scores land
investment opportunities, and runs a rigorous legal due-diligence checklist so no
disputed or encroached land ever reaches a recommendation.

## 0. Honest boundaries (non-negotiable design constraints)

1. **Public information only.** Gazettes, budgets, master plans, tenders,
   cabinet-decision press releases, RERA filings, court records. "Internal talks" of
   governments is non-public information — acting on it is legally dangerous
   (and unverifiable rumor in practice). The edge this system hunts is *reading the
   public record earlier and more completely than others*: draft master plans, land
   acquisition notifications, and tender awards are public months-to-years before
   prices fully adjust.
2. **The bot is a due-diligence assistant, not a lawyer.** It runs the checklist,
   pulls the public records, and flags risks — but every shortlisted parcel requires
   a written title opinion from a local advocate (ideally 30-year title search) and
   a licensed surveyor's demarcation before any money moves. The system's output for
   legal checks is a *risk report + question list for the lawyer*, never a clearance.
3. **Land is illiquid, lumpy, and unregistered-data-poor.** Price discovery is weak
   (registration values understate; asking prices overstate). All return math uses
   conservative haircuts and assumes 6–24 month exit timelines.

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Government Signal Monitor (daily/weekly)       │
│  Gazettes · budgets · cabinet releases · master plans       │
│  tenders (NHAI/rail/metro/airports) · land pooling ·        │
│  industrial policy · RERA · municipal upgrades              │
└──────────────┬──────────────────────────────────────────────┘
               │ Claude classifies → structured "development events"
┌──────────────▼──────────────────────────────────────────────┐
│              Corridor Scoring Engine                        │
│  Hyderabad-pattern template: infra + jobs + connectivity    │
│  + policy commitment + stage-of-cycle → corridor score      │
└──────────────┬──────────────────────────────────────────────┘
               │ ranked corridors/micro-markets
┌──────────────▼──────────────────────────────────────────────┐
│              Parcel Evaluation (when user has candidates)   │
│  Location score · price vs guidance value · zoning/master   │
│  plan overlay · LEGAL DUE-DILIGENCE ENGINE (checklist +     │
│  public-record pulls + red-flag detector)                   │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│   Output: corridor watchlist · parcel risk reports ·        │
│   lawyer question-list · entry/exit thesis with timeline    │
└─────────────────────────────────────────────────────────────┘
```

## 2. Data sources (all public)

| Signal | Source |
|---|---|
| Central infra | NHAI project/tender portal, Ministry of Railways (new lines, RRTS), AAI/greenfield airports (Bhogapuram, etc.), Gati Shakti announcements, DPIIT industrial corridors (NICDC), PM MITRA parks |
| State-level (AP/TG focus) | State gazettes, cabinet decision press notes, budget speeches (capex tables), APCRDA (Amaravati), APIIC/TGIIC industrial park allotments, HMDA/DTCP master plans, ORR/RRR alignments |
| Urban planning | Statutory master plans & draft revisions (objection periods = earliest public signal), municipal corporation upgrades (nagar panchayat → municipality → corporation), smart-city/AMRUT lists |
| Land records TG | Bhu-Bharati (Dharani successor) — ownership, prohibited-land lists |
| Land records AP | MeeBhoomi (adangal/1B), AP registration dept (encumbrance certificates online) |
| Litigation | eCourts case search (party/survey no.), high court cause lists, NCLT (builder insolvency) |
| Market prices | Registration dept guidance values (floor), portal listings (ceiling), RERA project filings (developer activity = demand proxy) |
| Jobs signal | Large office/factory leasing news, IT park allotments, PLI beneficiary plant locations |

## 3. The two engines (knowledge modules specify them)

- `knowledge/01-growth-corridor-analysis.md` — the Hyderabad case study distilled
  into a repeatable scoring template; stage-of-cycle framework (when land 10x's and
  when it stagnates); AP/TG current watch-map logic.
- `knowledge/02-legal-due-diligence.md` — full title/litigation/encroachment
  checklist (advocate-grade question list), state-specific record systems,
  red-flag taxonomy (assigned land, ULC, endowment/wakf, FTL/buffer zones, benami),
  and the RERA layer for developed plots.

## 4. Phased roadmap

| Phase | Scope |
|---|---|
| 1 | Signal monitor: scrape/ingest gazettes, tender portals, news for AP+TG; Claude event classifier; weekly digest |
| 2 | Corridor scoring engine + watch-map for AP/TG micro-markets; backfill 20 years of Hyderabad data to calibrate the template |
| 3 | Parcel evaluator: guidance-value comparison, master-plan overlay, legal checklist automation (EC pulls, prohibited-land list checks, eCourts search) |
| 4 | Portfolio layer: track owned parcels, exit-stage alerts (corridor maturing), liquidity/holding-cost math (vs. simply holding Nifty — the honest benchmark) |
| 5 | Extend beyond AP/TG to other state capitals & corridor cities |

## 5. Relationship to the stock advisor

Shared philosophy modules apply (process discipline, base rates, pre-mortems,
behavioral guards). Key shared lesson: land's historical mega-returns
(the Hyderabad stories) are *survivorship-biased and concentration-heavy* — the
system always benchmarks a land thesis against the boring alternative (index
equity) after holding costs, illiquidity, and legal risk, and sizes land as a
portfolio allocation decision, not an all-in bet.
