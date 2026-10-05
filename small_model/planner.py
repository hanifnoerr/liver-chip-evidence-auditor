"""Source-backed actions and the explicit policy used to train the small model."""

import json

ACTION_CODES = ["FIX", "INSPECT", "REPEAT", "RECOVER", "COMPARE", "EXTEND", "REPORT", "ABSTAIN"]
SYSTEM = "Choose one liver-chip audit action. Return only its code. Use the evidence, request and resource limits. Influence is not error; albumin is not clinical safety."
DEFINITIONS = "FIX correct blocked input; INSPECT review influential source records; REPEAT independently repeat an existing influential condition; RECOVER locate documented missing originals; COMPARE inspect disagreeing curve assumptions; EXTEND assess additional dose coverage with the laboratory; REPORT retain the current result and limitations; ABSTAIN decline an unsupported request."


def evidence_packet(analysis):
    primary = analysis.get("primary", {})
    counts = {}
    for kind in ["reading_deletion", "dose_deletion", "missing_probe", "model"]:
        counts[kind] = sum(item["changed"] for item in analysis.get("scenarios", []) if item["kind"] == kind)
    influential = []
    model_cards = []
    missing_cards = []
    for card in analysis.get("recommendations", []):
        if card["rule"] in ["reading_influence", "dose_dependence", "dose_coverage"]:
            influential.append(card)
        if card["rule"] in ["model_disagreement", "comparator_limit"]:
            model_cards.append(card)
        if card["rule"] == "missing_evidence":
            missing_cards.append(card)
    doses = analysis.get("doses", [])
    return {
        "blocked": bool(analysis["blocked"]),
        "state": primary.get("state", "unavailable"),
        "crossing_x_cmax": primary.get("crossing"),
        "dose_range_x_cmax": [doses[0], doses[-1]] if doses else [],
        "changed_scenarios": counts,
        "influential_conditions": len(influential),
        "missing_records": len(analysis.get("records", [])) and sum(row["missing"] for row in analysis["records"]),
        "model_concerns": len(model_cards),
        "influential_cards": influential,
        "missing_cards": missing_cards,
        "model_cards": model_cards,
    }


def eligible_actions(packet, resources):
    if packet["blocked"]:
        return ["FIX", "ABSTAIN"]
    allowed = ["REPORT", "ABSTAIN"]
    if resources["record_review"] and packet["influential_conditions"]:
        allowed.append("INSPECT")
    if resources["repeat_budget"] > 0 and packet["influential_conditions"]:
        allowed.append("REPEAT")
    if resources["missing_record_access"] and packet["missing_cards"]:
        allowed.append("RECOVER")
    if resources["record_review"] and packet["model_concerns"]:
        allowed.append("COMPARE")
    if resources["new_dose_allowed"] and packet["state"] in ["left_censored", "right_censored"]:
        allowed.append("EXTEND")
    return [code for code in ACTION_CODES if code in allowed]


def policy_action(packet, intent, resources):
    """Heuristic training target with known intent, not biological ground truth."""
    if packet["blocked"]:
        return "FIX"
    if intent == "unsupported":
        return "ABSTAIN"
    allowed = eligible_actions(packet, resources)
    if intent == "bounded_report":
        return "REPORT"
    if intent == "model_review" and "COMPARE" in allowed:
        return "COMPARE"
    if intent == "recover" and "RECOVER" in allowed:
        return "RECOVER"
    if packet["changed_scenarios"]["missing_probe"] and "RECOVER" in allowed:
        return "RECOVER"
    if intent in ["repeat", "finite_crossing"] and "REPEAT" in allowed:
        return "REPEAT"
    if "INSPECT" in allowed:
        return "INSPECT"
    if "COMPARE" in allowed:
        return "COMPARE"
    if intent == "finite_crossing" and "EXTEND" in allowed:
        return "EXTEND"
    return "REPORT"


def infer_intent(request):
    text = request.lower()
    if any(phrase in text for phrase in ["declare safe", "clinically safe", "patient", "discard", "delete the", "remove the inconvenient", "certify safety", "inconvenient point", "approve this medicine"]):
        return "unsupported"
    if any(phrase in text for phrase in ["bounded", "censored", "no finite", "do not need a finite", "don't need a finite", "without a finite", "range-qualified"]):
        return "bounded_report"
    if any(phrase in text for phrase in ["curve assumptions", "curve models", "model disagreement", "alternative fits", "comparator"]):
        return "model_review"
    if any(phrase in text for phrase in ["missing", "absent", "original values"]):
        return "recover"
    if any(phrase in text for phrase in ["finite", "bracket", "crossing estimate", "numerical dose", "half its reference"]):
        return "finite_crossing"
    if any(phrase in text for phrase in ["repeat", "replicate", "confirmation"]):
        return "repeat"
    return "review"


def rule_action(packet, request, resources):
    return policy_action(packet, infer_intent(request), resources)


def fixed_action(packet, resources):
    allowed = eligible_actions(packet, resources)
    for code in ["FIX", "INSPECT", "RECOVER", "COMPARE", "REPEAT", "EXTEND", "REPORT", "ABSTAIN"]:
        if code in allowed:
            return code


def prompt_messages(packet, request, resources):
    evidence = {}
    for key in ["blocked", "state", "crossing_x_cmax", "dose_range_x_cmax", "changed_scenarios", "influential_conditions", "missing_records", "model_concerns"]:
        evidence[key] = packet[key]
    evidence["allowed_actions"] = eligible_actions(packet, resources)
    user_text = DEFINITIONS + "\nEvidence: " + json.dumps(evidence, separators=(",", ":"))
    user_text += "\nResources: " + json.dumps(resources, separators=(",", ":"))
    user_text += "\nResearcher request: " + request + "\nAction code:"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_text}]


def guard_action(raw_action, packet, request, resources):
    allowed = eligible_actions(packet, resources)
    unsupported = infer_intent(request) == "unsupported"
    forbidden = raw_action not in allowed or (packet["blocked"] and raw_action != "FIX") or (unsupported and raw_action not in ["ABSTAIN", "FIX"])
    if forbidden:
        return rule_action(packet, request, resources), True
    return raw_action, False


def render_action(action, analysis, resources=None):
    """Copy numerical evidence and references; never use model-generated numbers."""
    packet = evidence_packet(analysis)
    primary = analysis.get("primary", {})
    doses = analysis.get("doses", [])
    state = primary.get("state", "unavailable")
    crossing = primary.get("crossing")
    dose_range = f"{doses[0]:g}–{doses[-1]:g}× unbound Cmax" if doses else "an unavailable dose range"
    if analysis["blocked"]:
        conclusion = "The input is blocked; no usable response estimate can be reported."
    elif state == "within_range" and crossing is not None:
        conclusion = f"The primary fit estimates a 50% albumin crossing at {crossing:.2f}× unbound Cmax within the measured {dose_range} range."
    elif state == "right_censored":
        conclusion = f"The primary fitted albumin response stays above 50% across {dose_range}. A crossing was not observed within this range; a finite crossing cannot be reported."
    elif state == "left_censored":
        conclusion = f"The primary fitted albumin response is already at or below 50% at the lowest measured dose. The measured range is {dose_range}; the crossing cannot be located within it."
    else:
        conclusion = "The primary model did not produce a usable response estimate."
    card = None
    if action in ["INSPECT", "REPEAT"]:
        card = packet["influential_cards"][0]
    elif action == "RECOVER":
        card = packet["missing_cards"][0]
    elif action == "COMPARE":
        card = packet["model_cards"][0]
    elif action == "FIX":
        card = analysis["recommendations"][0]
    if card:
        result = dict(card)
        if action == "INSPECT":
            result["action"] = "Inspect the linked original readings and any available sampling, assay and device records. Check the linked sensitivity calculation and retain all original readings in the analysis."
        if action == "REPEAT":
            doses = ", ".join(f"{dose:g}×" for dose in card["dose_cmax_multiples"])
            result["title"] = "Consider an independent repeat at " + doses + " unbound Cmax"
            result["action"] = "If experimentally appropriate, independently repeat this existing condition with documented sampling and assay controls. Retain all original readings. This is an influence-based heuristic, not an optimal dose selection."
    else:
        title = {"REPORT": "Retain the result and its evidence limitations", "EXTEND": "Assess whether additional dose coverage is appropriate", "ABSTAIN": "The requested conclusion is outside this tool's scope"}[action]
        text = {
            "REPORT": "Report the current crossing or censoring state together with all identified sensitivity and unassessed experimental evidence. Scenario agreement does not establish drug safety.",
            "EXTEND": "Resolve the identified evidence concerns first. If a finite crossing is required, discuss additional dose coverage with the laboratory. This tool does not specify a new exposure or establish its experimental suitability.",
            "ABSTAIN": "This analysis cannot certify clinical safety or justify removing an inconvenient reading. Review the original evidence and involve the responsible scientist.",
        }[action]
        ids = []
        scenario_ids = []
        for source_card in analysis.get("recommendations", []):
            ids.extend(source_card["source_record_ids"])
            scenario_ids.extend(source_card["scenario_ids"])
        result = {"id": "planner:" + action, "title": title, "reason": conclusion, "action": text, "source_record_ids": sorted(set(ids)), "scenario_ids": sorted(set(scenario_ids)), "dose_cmax_multiples": doses, "check_codes": analysis.get("unassessed_evidence", []), "interpretation": "Albumin response alone does not establish liver injury or clinical safety."}
    result["action_code"] = action
    result["conclusion"] = conclusion
    result["evidence_summary"] = [item["reason"] for item in analysis.get("recommendations", [])] if action == "REPORT" else []
    result["limitations"] = [{"label": item["label"], "evidence": item["evidence"]} for item in analysis.get("checklist", []) if item["status"] == "Not assessed"]
    result["feasibility"] = {
        "FIX": "Input correction is required before any fitted result can be used.",
        "INSPECT": "Existing-record review is enabled. This step does not require a new experiment.",
        "REPEAT": "One independent repeat at an existing dose is available. The named condition is already in the measured range.",
        "RECOVER": "Archive access is enabled. This step looks for documented originals rather than inventing replacement values.",
        "COMPARE": "Existing-record review is enabled. The alternative fits can be inspected without a new experiment.",
        "EXTEND": "You allow discussion of additional dose coverage with the laboratory. Experimental suitability still needs assessment.",
        "REPORT": "Reporting uses the current evidence and requires no additional measurements.",
        "ABSTAIN": "The requested conclusion is unsupported regardless of the available resources.",
    }[action] if resources is not None else ""
    result["future_action"] = ""
    if resources is not None and action == "INSPECT" and not resources["repeat_budget"]:
        result["future_action"] = "If an independent repeat becomes available and the concern remains unresolved, assess a repeat at the named existing dose with the laboratory. This is an influence-based heuristic, not optimal experimental design."
    return result
