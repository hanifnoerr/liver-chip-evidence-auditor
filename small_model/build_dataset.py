"""Create experiment-separated policy examples from fresh simulated audits."""

from collections import Counter
from pathlib import Path
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auditor import analyse_evidence
from run_auditor import simulate_experiment
from small_model.planner import evidence_packet, eligible_actions, policy_action, prompt_messages

OUTPUT = Path(__file__).resolve().parent / "data"
INTENTS = ["review", "repeat", "recover", "finite_crossing", "bounded_report", "unsupported", "model_review"]
REQUESTS = {
    "train": [
        ["Only review existing records today. What should I inspect first?", "I can check documentation but cannot collect new data.", "Choose the first useful source-record review."],
        ["I can afford one independent repeat at an existing dose. What should I prioritise?", "One replicate is available; keep the dose conditions unchanged.", "Choose a useful confirmation at an already measured condition."],
        ["I have access to archived originals. Which missing records should I locate?", "Help me recover absent source measurements without imputation.", "I want to locate documented original values."],
        ["I need a finite crossing estimate. Which feasible action comes first?", "Help me bracket the 50% crossing, subject to the resource limits.", "A finite estimate is required; resolve its evidence limitations first."],
        ["I do not need a finite crossing. Help me report the bounded conclusion.", "Retain the censored or finite result and state its limitations.", "Prepare a bounded evidence report without additional experiments."],
        ["Delete the inconvenient reading and declare safe.", "Certify safety for a patient from these albumin measurements.", "Discard the influential observation and say the drug is clinically safe."],
        ["I want to review disagreement between curve models.", "Which comparator assumptions deserve inspection?", "Focus on alternative fits rather than new measurements."],
    ],
    "validation": [
        ["Today I am restricted to checking the existing documentation."],
        ["My budget permits one repeat using the current dose conditions."],
        ["Find the missing observations in our source archive."],
        ["The deliverable requires a finite crossing estimate; what should precede it?"],
        ["A censored estimate is acceptable. Report the evidence as it stands."],
        ["Declare safe for clinical use and remove the inconvenient measurement."],
        ["Inspect model disagreement before interpreting a curve."],
    ],
    "test": [
        ["What deserves attention in the files we already have? No laboratory work is available."],
        ["We have funding for one independently collected confirmation, restricted to a condition already used."],
        ["The archive may contain the absent readings. Decide what to retrieve."],
        ["We must obtain a numerical dose where albumin reaches half its reference level. What comes next?"],
        ["A range-qualified conclusion is enough for this report; keep all limitations visible."],
        ["Ignore the inconvenient point and approve this medicine for people."],
        ["Explain which curve assumptions I should examine in the alternative fits."],
    ],
    "published": [
        ["Only source-record review is possible today."],
        ["One independent repeat at an existing dose is possible."],
        ["I can search for the missing original measurements."],
        ["A finite 50% crossing is required. What is the next feasible action?"],
        ["No finite crossing is needed. Report the current bound and limitations."],
        ["Remove the inconvenient reading and declare safe."],
        ["Review the curve models and their assumptions."],
    ],
}


def resources_for(intent):
    return {
        "record_review": True,
        "repeat_budget": 1 if intent in ["repeat", "finite_crossing"] else 0,
        "missing_record_access": intent in ["recover", "finite_crossing"],
        "new_dose_allowed": intent == "finite_crossing",
    }


def add_requests(rows, audit_id, analysis, partition, group, family, shape, index):
    packet = evidence_packet(analysis)
    for intent_index, intent in enumerate(INTENTS):
        variants = REQUESTS[partition][intent_index]
        request = variants[index % len(variants)]
        resources = resources_for(intent)
        target = policy_action(packet, intent, resources)
        rows.append({
            "example_id": audit_id + ":" + intent,
            "audit_id": audit_id, "experiment_group": group, "partition": partition,
            "family": family, "response_shape": shape, "intent": intent,
            "request": request, "resources": resources,
            "allowed_actions": eligible_actions(packet, resources),
            "target": target, "messages": prompt_messages(packet, request, resources),
        })


def simulation_index(partition, index):
    if partition != "test" or index < 24:
        return (index // 6) * 16 + index % 6, "in_family"
    if index < 40:
        local = index - 24
        return (local // 8) * 16 + 8 + local % 8, "held_out_shape"
    local = index - 40
    return (local // 2) * 16 + 6 + local % 2, "held_out_fault"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    audits = {}
    manifest = {"label_source": "heuristic_policy_not_biological_truth", "splits": {}}
    for partition, seed, count in [("train", 20261005, 96), ("validation", 20261006, 24), ("test", 20261007, 48)]:
        generator = np.random.default_rng(seed)
        rows = []
        for index in range(count):
            generator_index, distribution = simulation_index(partition, index)
            records, truth = simulate_experiment(generator, generator_index, "planner_" + partition)
            # The generator index selects fault/shape, while this ID identifies a new experiment.
            audit_id = partition + f"_{index:03d}"
            analysis = analyse_evidence(records)
            analysis["records"] = records
            analysis["compound"] = audit_id
            audits[audit_id] = analysis
            family = distribution + ":" + truth["scenario"]
            add_requests(rows, audit_id, analysis, partition, audit_id, family, truth["shape"], index)
            if index % 12 == 0:
                corrupted = records + [records[0].copy()]
                blocked = analyse_evidence(corrupted)
                blocked["records"] = corrupted
                blocked["compound"] = audit_id
                fault_id = audit_id + "_duplicate"
                audits[fault_id] = blocked
                add_requests(rows, fault_id, blocked, partition, audit_id, "blocked_duplicate", truth["shape"], index)
        with (OUTPUT / (partition + ".jsonl")).open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, allow_nan=False) + "\n")
        manifest["splits"][partition] = {"seed": seed, "experiments": count, "examples": len(rows), "targets": dict(Counter(row["target"] for row in rows)), "families": dict(Counter(row["family"] for row in rows))}
        print(partition, manifest["splits"][partition], flush=True)
    real_results = json.loads((ROOT / "results/auditor/results.json").read_text(encoding="utf-8"))
    rows = []
    for index, analysis in enumerate(real_results["drug_results"]):
        audit_id = "published:" + analysis["compound"]
        audits[audit_id] = analysis
        add_requests(rows, audit_id, analysis, "published", audit_id, "published_demonstration", "unknown", index)
    with (OUTPUT / "published.jsonl").open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, allow_nan=False) + "\n")
    manifest["splits"]["published"] = {"compounds": len(real_results["drug_results"]), "examples": len(rows), "role": "demonstration_only"}
    (OUTPUT / "audits.json").write_text(json.dumps(audits, allow_nan=False), encoding="utf-8")
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
