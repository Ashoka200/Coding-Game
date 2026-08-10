# 02 — Legal Due Diligence (title, litigation, encroachment — the veto engine)

Doctrine: **in Indian land, the legal check IS the investment decision.** A mediocre
location with clean title beats a great location with a title defect — the defect
doesn't discount the price, it can zero it. This module makes the bot a rigorous
due-diligence assistant; final clearance always comes from a local advocate's written
title opinion (30-year search) + licensed surveyor. The bot's deliverable is a
risk report and a question list the lawyer must answer.

## The checklist (every parcel, no exceptions)

### A. Title chain
1. **30-year link documents:** every sale/gift/partition/inheritance deed in sequence;
   any gap or unregistered link = flag. Verify seller's name matches records exactly.
2. **Encumbrance Certificate (EC)** for 30 years from registration dept (online in
   AP/TG): mortgages, prior sales, agreements — any live encumbrance = stop.
3. **Revenue records:** pattadar passbook / 1B & adangal (AP: MeeBhoomi;
   TG: Bhu-Bharati) — owner name, extent, classification must match deeds. Mutation
   completed after every past transfer; pending mutation = flag.
4. **Heirship:** inherited land needs legal-heir certificate + *all* heirs signing
   (including married daughters — equal coparcenary rights post-2005 amendment;
   missing-heir signatures are the classic future-litigation seed). Minor heirs need
   court permission. Sale by GPA holder: verify GPA is registered, alive (principal
   not deceased), and irrevocable-with-consideration; **GPA "sales" are not title**
   (Suraj Lamp, SC 2011).

### B. Prohibited / restricted categories (the red-flag taxonomy)
- **Assigned land** (govt-assigned to landless poor): non-transferable under POT Acts —
  purchase is void; check prohibited-property lists (Section 22A registers).
- **Government/poramboke, endowment (temple), and wakf land:** unsaleable regardless
  of paperwork shown; wakf claims can surface decades later. Cross-check endowment
  and wakf board lists.
- **Ceiling-surplus (ULC) land, Bhoodan land, tribal land in scheduled areas**
  (non-tribal purchase barred), **inam land** without occupancy-rights conversion.
- **Water bodies:** FTL (full tank level) and buffer zones of lakes/tanks
  (HMDA lake lists), river beds, nala margins — construction-banned and
  demolition-prone even with registered deeds.
- **Forest/military:** reserved forest notifications, defense land boundaries.
- Agricultural land: verify buyer eligibility rules of that state and NALA/land-use
  conversion status & fees for non-agricultural use.

### C. Litigation & encroachment
1. **eCourts search** by survey number + all sellers' names (civil suits, partition
   suits, injunctions); High Court cause lists; Lok Adalat awards.
2. **Lis pendens check** and Section 52 TPA risk: pending-suit purchases bind the buyer.
3. **Attachment / acquisition:** revenue-recovery attachments, bank SARFAESI notices,
   and land-acquisition notifications (a corridor bot irony: the same highway that
   makes land valuable may be *acquiring* this parcel — check alignment gazette
   notifications against the survey number).
4. **Physical verification (irreplaceable by any database):** licensed surveyor
   demarcation vs record extent; possession matches title (who actually farms/occupies
   it?); boundary disputes with neighbors; access road exists *in records* (a plot
   without recorded access is landlocked — huge value trap); local enquiry (talk to
   village revenue officials & neighbors — India's cheapest and best fraud detector).
5. **Encroachment on the parcel** (occupants can ripen into rights/political
   protection) and **by the parcel** (structure over govt land = demolition risk).

### D. For plotted developments / apartments (the RERA layer)
- RERA registration of the layout/project (AP RERA / TG RERA portals): approvals,
  litigation disclosures, promoter track record, quarterly progress.
- Layout approval authority (HMDA/DTCP/CRDA/local body) — unapproved ("gram
  panchayat") layouts trade cheap for a reason: regularization is a lottery.
- Builder solvency: NCLT insolvency search on the promoter entity.

## Red-flag severity model (engine spec)

- **VETO (walk away):** prohibited category hit, live litigation on title, seller ≠
  record owner, GPA-only chain, FTL/buffer overlap, acquisition notification overlap,
  no recorded access.
- **RESOLVE-FIRST (conditional):** pending mutation, missing heir signature
  (obtainable), expired EC gap, NALA conversion pending — priced and time-boxed;
  money only via escrow/registered agreement with conditions.
- **MONITOR:** master-plan zoning mismatch with intended use, minor extent
  discrepancies (<2%), old resolved litigation (get certified final orders).

## Transaction hygiene (the bot enforces the process)

- Registered agreement-to-sell with clear conditions precedent; payments traceable
  (never cash beyond legal limits — cash components destroy both legal standing and
  future capital-gains basis); TDS u/s 194-IA where applicable (>₹50L, 1%).
- Post-registration task list auto-generated: mutation application, passbook update,
  fencing + boundary stones + signage, property-tax/land-revenue receipts in own
  name, periodic physical inspection schedule (encroachment prevention is a
  *maintenance activity*), and EC re-pull 3 months post-sale (fraud double-sales
  surface there).

## The standing disclaimer in every parcel report

"This is a public-records risk screen, not legal advice. Proceed only after a
written title opinion from a local property advocate based on original documents
and a 30-year search, and a licensed surveyor's demarcation."
