"""Re-audit documented evidence revisions while retaining the original case."""

import csv
import io

from auditor import analyse_evidence, conclusion_changed


def normalise_records(records):
    normalised = []
    for original in records:
        row = dict(original)
        if not isinstance(row["missing"], bool):
            flag = str(row["missing"]).lower()
            if flag not in ["true", "false", "1", "0"]:
                raise ValueError("Missing must be True or False.")
            row["missing"] = flag in ["true", "1"]
        row["dose_cmax_multiple"] = float(row["dose_cmax_multiple"])
        row["day"] = float(row["day"])
        row["value"] = "" if row["missing"] else float(row["value"])
        row["source_row"] = str(row.get("source_row", ""))
        normalised.append(row)
    return normalised


def audit_case(records, allow_blocked=False):
    if not isinstance(records, list) or not records:
        raise ValueError("A complete case with source records is required.")
    records = normalise_records(records)
    compounds = {row["compound"] for row in records}
    if len(compounds) != 1:
        raise ValueError("A reassessment must use one compound.")
    analysis = analyse_evidence(records)
    if analysis["blocked"] and not allow_blocked:
        messages = [issue["message"] for issue in analysis["issues"] if issue["severity"] == "blocked"]
        raise ValueError(" ".join(messages))
    analysis["records"] = records
    analysis["compound"] = records[0]["compound"]
    if analysis["blocked"]:
        analysis["doses"] = []
        analysis["primary"] = {"state": "fit_failed", "crossing": None, "success": False}
    return analysis


def read_case_csv(text, compound):
    records = []
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        if row["compound"] == compound and row["endpoint"] == "albumin_percent":
            records.append(row)
    if not records:
        raise ValueError(f"The CSV has no albumin records for {compound}. Keep the same compound name as the original case.")
    return records


def record_changes(original, revised):
    before = {row["source_record_id"]: row for row in original}
    after = {row["source_record_id"]: row for row in revised}
    removed = sorted(set(before) - set(after))
    if removed:
        raise ValueError("Retain every baseline source record. This revision removes: " + ", ".join(removed))
    changes = []
    for record_id, row in after.items():
        previous = before.get(record_id)
        if previous is not None and not previous["missing"] and row["missing"]:
            raise ValueError(f"An observed baseline reading cannot be changed to missing: {record_id}. Retain it and document the concern separately.")
        fields = []
        for field in sorted(set(row) | set(previous or {})):
            old_value = previous.get(field, "") if previous is not None else None
            new_value = row.get(field, "")
            if old_value != new_value:
                fields.append({"field": field, "before": old_value, "after": new_value})
        old_count = sum(item["source_record_id"] == record_id for item in original)
        new_count = sum(item["source_record_id"] == record_id for item in revised)
        if previous is not None and old_count != new_count:
            fields.append({"field": "input_occurrences", "before": old_count, "after": new_count})
        if not fields:
            continue
        kind = "added" if previous is None else "recovered" if previous["missing"] and not row["missing"] else "modified"
        changes.append({"source_record_id": record_id, "source_location": row["source_sheet"] + "!" + row["source_cell"], "kind": kind, "fields": fields})
    return changes


def reassess_case(baseline_records, updated_csv, evidence_reference, compatibility_note, action=None, action_doses=None):
    for value, label in [(evidence_reference, "source reference"), (compatibility_note, "compatibility note")]:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
            raise ValueError(f"Document the {label} in 1–2000 characters.")
    if not isinstance(updated_csv, str):
        raise ValueError("Supply the updated CSV as text.")
    baseline = audit_case(baseline_records, allow_blocked=True)
    updated = audit_case(read_case_csv(updated_csv, baseline["compound"]))
    changes = record_changes(baseline["records"], updated["records"])
    if not changes:
        raise ValueError("No changed or added records were found for this compound. Record an outcome without changing the analysis instead.")
    added_ids = {item["source_record_id"] for item in changes if item["kind"] == "added"}
    new_observations = [row for row in updated["records"] if row["source_record_id"] in added_ids and not row["missing"]]
    if action == "RECOVER" and not any(item["kind"] == "recovered" for item in changes):
        raise ValueError("A recovery outcome requires a missing baseline original to become observed under its existing source ID.")
    if action == "REPEAT":
        named_doses = set(action_doses or []) & set(baseline["doses"])
        if not any(row["dose_cmax_multiple"] in named_doses for row in new_observations):
            raise ValueError("A repeat outcome requires an added observed original with a new source ID at the named existing dose.")
    if action == "EXTEND" and not any(row["dose_cmax_multiple"] not in baseline["doses"] for row in new_observations):
        raise ValueError("A new-dose outcome requires an added observed original at a dose not observed in the baseline.")
    if action == "FIX" and not baseline["blocked"]:
        raise ValueError("A corrected-input outcome requires a blocked baseline. Use a documented evidence correction for an otherwise usable case.")
    if action is not None and action not in ["INSPECT", "RECOVER", "REPEAT", "EXTEND", "FIX"]:
        raise ValueError("This action records a decision or interpretation without changing measurements. Start a new evidence-review action for a data update.")
    measurements_changed = bool(new_observations)
    for change in changes:
        if change["kind"] == "recovered" or (change["kind"] != "added" and any(field["field"] in ["value", "missing", "dose_cmax_multiple", "day", "endpoint", "dose_unit", "response_unit"] for field in change["fields"])):
            measurements_changed = True
    original_checks = {item["code"]: item for item in baseline["checklist"]}
    check_changes = []
    for item in updated["checklist"]:
        original = original_checks.get(item["code"])
        if original and (original["status"] != item["status"] or original["evidence"] != item["evidence"]):
            check_changes.append({"code": item["code"], "label": item["label"], "before": original["status"], "after": item["status"], "before_evidence": original["evidence"], "after_evidence": item["evidence"]})
    return {
        "baseline": baseline,
        "updated": updated,
        "record_changes": changes,
        "check_changes": check_changes,
        "material_conclusion_change": conclusion_changed(baseline["primary"], updated["primary"]),
        "evidence_version_changed": True,
        "measurements_changed": measurements_changed,
        "evidence_reference": evidence_reference.strip(),
        "compatibility_note": compatibility_note.strip(),
        "compatibility_status": "researcher_reported_not_independently_verified",
        "interpretation": "This compares two supplied evidence versions. A changed conclusion or fewer triggered checks does not establish experimental validity, biological independence or drug safety.",
    }
