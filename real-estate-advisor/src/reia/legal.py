"""Legal due-diligence engine (knowledge 02) — the veto layer.

The checklist is data: each item has an id, a question (what to verify and where),
and a severity if the answer is bad. `evaluate()` turns a dict of answers
(True=verified clean, False=problem found, None=not yet checked) into a verdict:

    VETO                 — walk away; a veto item failed
    RESOLVE_FIRST        — conditional items failed; resolve before money moves
    CLEAR_PENDING_LAWYER — screen clean; proceed to advocate's title opinion

Unchecked VETO-class items keep the parcel at RESOLVE_FIRST — silence is never
clearance. The best possible output still requires a human lawyer (knowledge 02).
"""
from __future__ import annotations

VETO, RESOLVE, MONITOR = "veto", "resolve", "monitor"

CHECKLIST: list[dict] = [
    # A. Title chain
    {"id": "title_chain_30y", "sev": VETO,
     "q": "30-year link documents complete, every transfer registered, no gaps?"},
    {"id": "ec_30y_clean", "sev": VETO,
     "q": "Encumbrance Certificate (30y) shows no live mortgage/agreement/prior sale?"},
    {"id": "seller_is_record_owner", "sev": VETO,
     "q": "Seller's name matches pattadar passbook/1B-adangal (MeeBhoomi/Bhu-Bharati) exactly?"},
    {"id": "no_gpa_only_chain", "sev": VETO,
     "q": "No link in the chain rests on GPA alone (Suraj Lamp: GPA is not title)?"},
    {"id": "all_heirs_signed", "sev": RESOLVE,
     "q": "Inherited land: legal-heir certificate + ALL heirs (incl. daughters) signing?"},
    {"id": "mutation_complete", "sev": RESOLVE,
     "q": "Mutation completed for every past transfer (no pending mutations)?"},
    # B. Prohibited categories
    {"id": "not_assigned_land", "sev": VETO,
     "q": "Not govt-assigned land / not on Section 22A prohibited-property list?"},
    {"id": "not_endowment_wakf", "sev": VETO,
     "q": "Not temple/endowment or wakf land (checked both boards' lists)?"},
    {"id": "not_ceiling_bhoodan_tribal", "sev": VETO,
     "q": "Not ULC-surplus, Bhoodan, inam-unconverted, or tribal land in scheduled area?"},
    {"id": "outside_ftl_buffer", "sev": VETO,
     "q": "Outside lake FTL and buffer zones / nala margins (HMDA lake list checked)?"},
    {"id": "not_forest_defense", "sev": VETO,
     "q": "Clear of reserved forest notifications and defense land?"},
    {"id": "nala_conversion", "sev": RESOLVE,
     "q": "Agricultural→non-agricultural (NALA) conversion done or not needed?"},
    # C. Litigation & possession
    {"id": "no_litigation", "sev": VETO,
     "q": "eCourts search by survey no. + sellers' names shows no pending suit/injunction?"},
    {"id": "no_acquisition_overlap", "sev": VETO,
     "q": "No land-acquisition notification covers this survey number (check alignments)?"},
    {"id": "no_attachment", "sev": VETO,
     "q": "No revenue attachment / bank SARFAESI notice on the property?"},
    {"id": "recorded_access", "sev": VETO,
     "q": "Access road exists IN RECORDS (not just on the ground)?"},
    {"id": "possession_matches", "sev": RESOLVE,
     "q": "Surveyor demarcation matches record extent; possession matches title?"},
    {"id": "no_encroachment", "sev": RESOLVE,
     "q": "No occupants/encroachment on the parcel; no structure over govt land?"},
    {"id": "local_enquiry_clean", "sev": MONITOR,
     "q": "Village revenue officials + neighbours corroborate ownership story?"},
    # D. Layouts/projects only
    {"id": "layout_approved", "sev": RESOLVE, "applies": "layout",
     "q": "Layout approved by HMDA/DTCP/CRDA (not unapproved gram-panchayat)?"},
    {"id": "rera_registered", "sev": RESOLVE, "applies": "layout",
     "q": "RERA-registered with clean promoter disclosures; promoter not in NCLT?"},
]

DISCLAIMER = ("This is a public-records risk screen, not legal advice. Proceed only "
              "after a written title opinion from a local property advocate based on "
              "original documents and a 30-year search, and a licensed surveyor's "
              "demarcation.")


def evaluate(answers: dict[str, bool | None], parcel_type: str = "raw_land") -> dict:
    """answers: {item_id: True(clean) | False(problem) | None(unchecked)}."""
    failed_veto, failed_resolve, failed_monitor, unchecked = [], [], [], []
    for item in CHECKLIST:
        if item.get("applies") == "layout" and parcel_type != "layout":
            continue
        ans = answers.get(item["id"])
        if ans is False:
            {VETO: failed_veto, RESOLVE: failed_resolve,
             MONITOR: failed_monitor}[item["sev"]].append(item)
        elif ans is None:
            unchecked.append(item)

    if failed_veto:
        verdict = "VETO"
    elif failed_resolve or any(i["sev"] == VETO for i in unchecked):
        verdict = "RESOLVE_FIRST"      # unchecked veto items ≠ clean
    else:
        verdict = "CLEAR_PENDING_LAWYER"

    return {
        "verdict": verdict,
        "failed_veto": [i["id"] for i in failed_veto],
        "failed_resolve": [i["id"] for i in failed_resolve],
        "failed_monitor": [i["id"] for i in failed_monitor],
        "unchecked": [i["id"] for i in unchecked],
        "lawyer_questions": [i["q"] for i in failed_veto + failed_resolve + unchecked],
        "disclaimer": DISCLAIMER,
    }


def blank_answers(parcel_type: str = "raw_land") -> dict[str, None]:
    return {i["id"]: None for i in CHECKLIST
            if i.get("applies") != "layout" or parcel_type == "layout"}
