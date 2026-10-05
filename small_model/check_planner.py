"""Check split separation, action constraints and real source references."""

from pathlib import Path
import json

from small_model.planner import ACTION_CODES, evidence_packet, eligible_actions, guard_action, render_action

ROOT = Path(__file__).resolve().parent


def main():
    audits = json.loads((ROOT / "data/audits.json").read_text(encoding="utf-8"))
    group_sets = []
    row_count = 0
    for partition in ["train", "validation", "test", "published"]:
        rows = [json.loads(line) for line in (ROOT / f"data/{partition}.jsonl").read_text(encoding="utf-8").splitlines()]
        groups = set()
        for row in rows:
            groups.add(row["experiment_group"])
            analysis = audits[row["audit_id"]]
            packet = evidence_packet(analysis)
            allowed = eligible_actions(packet, row["resources"])
            assert row["target"] in allowed, row["example_id"]
            assert row["allowed_actions"] == allowed
            for code in allowed:
                action = render_action(code, analysis)
                source_ids = {record["source_record_id"] for record in analysis["records"]}
                scenario_ids = {scenario["scenario_id"] for scenario in analysis["scenarios"]}
                assert set(action["source_record_ids"]) <= source_ids
                assert set(action["scenario_ids"]) <= scenario_ids
            for code in ACTION_CODES:
                delivered, fallback = guard_action(code, packet, row["request"], row["resources"])
                assert delivered in allowed
                if row["target"] in ["FIX", "ABSTAIN"]:
                    assert delivered == row["target"], (row["example_id"], code, delivered)
                if code not in allowed:
                    assert fallback
            row_count += 1
        for earlier in group_sets:
            assert not earlier.intersection(groups), "An experiment crosses partitions"
        group_sets.append(groups)
    clozapine = audits["published:Clozapine"]
    packet = evidence_packet(clozapine)
    review = {"record_review": True, "repeat_budget": 0, "missing_record_access": False, "new_dose_allowed": False}
    repeat = dict(review, repeat_budget=1)
    assert "REPEAT" not in eligible_actions(packet, review)
    assert "REPEAT" in eligible_actions(packet, repeat)
    action = render_action("REPEAT", clozapine)
    assert "ewart2022_supp8_ALBUMIN_C12" in action["source_record_ids"]
    assert action["dose_cmax_multiples"] == [300.0]
    original_cards = json.dumps(clozapine["recommendations"], sort_keys=True)
    inspect = render_action("INSPECT", clozapine, review)
    assert "repeat" not in inspect["action"].lower()
    assert "does not require a new experiment" in inspect["feasibility"]
    assert "repeat becomes available" in inspect["future_action"]
    assert not render_action("INSPECT", clozapine, repeat)["future_action"]
    report = render_action("REPORT", clozapine, review)
    assert "1–300× unbound Cmax" in report["conclusion"]
    assert "stays above 50%" in report["conclusion"]
    assert "ALBUMIN!C12" in " ".join(report["evidence_summary"])
    assert len(report["limitations"]) == 5
    assert json.dumps(clozapine["recommendations"], sort_keys=True) == original_cards
    pioglitazone = render_action("REPORT", audits["published:Pioglitazone"], review)
    assert "292.51× unbound Cmax" in pioglitazone["conclusion"]
    assert "ALBUMIN!C39" in " ".join(pioglitazone["evidence_summary"])
    print(f"Checked {row_count} examples: separate experiment groups, eligible targets and valid source/scenario references.")
    print("Resource-aware rendering and source-specific bounded reports passed; original audit cards remain unchanged.")


if __name__ == "__main__":
    main()
