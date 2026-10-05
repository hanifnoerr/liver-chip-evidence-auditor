"""Compare raw model choices, guarded choices and request-aware rules."""

from pathlib import Path
import argparse
import json
import statistics

from small_model.planner import evidence_packet, fixed_action, guard_action, render_action, rule_action

ROOT = Path(__file__).resolve().parent


def summarize(rows, field):
    correct = sum(row[field] == row["target"] for row in rows)
    by_action = {}
    by_family = {}
    for group_key, groups in [("target", by_action), ("family", by_family)]:
        for group in sorted(set(row[group_key] for row in rows)):
            selected = [row for row in rows if row[group_key] == group]
            matched = sum(row[field] == row["target"] for row in selected)
            groups[group] = {"n": len(selected), "correct": matched, "agreement": matched / len(selected)}
    return {"n": len(rows), "correct": correct, "agreement": correct / len(rows), "by_action": by_action, "by_family": by_family}


def evaluate(partition, runtime=None, limit=None):
    examples = [json.loads(line) for line in (ROOT / f"data/{partition}.jsonl").read_text(encoding="utf-8").splitlines()]
    if limit is not None:
        examples = examples[:limit]
    audits = json.loads((ROOT / "data/audits.json").read_text(encoding="utf-8"))
    decisions = []
    for index, example in enumerate(examples):
        analysis = audits[example["audit_id"]]
        packet = evidence_packet(analysis)
        result = {key: example[key] for key in ["example_id", "audit_id", "family", "response_shape", "intent", "target", "allowed_actions"]}
        result["fixed"] = fixed_action(packet, example["resources"])
        result["rules"] = rule_action(packet, example["request"], example["resources"])
        if runtime is not None:
            raw, details = runtime.choose(packet, example["request"], example["resources"])
            delivered, fallback = guard_action(raw, packet, example["request"], example["resources"])
            result.update(details)
            result.update(raw=raw, delivered=delivered, fallback=fallback, raw_ineligible=raw not in example["allowed_actions"])
            action = render_action(delivered, analysis)
            source_ids = {record["source_record_id"] for record in analysis["records"]}
            scenario_ids = {scenario["scenario_id"] for scenario in analysis["scenarios"]}
            result["references_valid"] = set(action["source_record_ids"]) <= source_ids and set(action["scenario_ids"]) <= scenario_ids
            result["action"] = action
        decisions.append(result)
        if index % 25 == 0:
            print(f"{partition}: {index + 1}/{len(examples)}", flush=True)
    summary = {"partition": partition, "label_source": "heuristic_policy_not_biological_truth", "limited_run": limit is not None}
    summary["fixed"] = summarize(decisions, "fixed")
    summary["rules"] = summarize(decisions, "rules")
    if runtime is not None:
        summary["raw"] = summarize(decisions, "raw")
        summary["delivered"] = summarize(decisions, "delivered")
        summary["fallback_count"] = sum(row["fallback"] for row in decisions)
        summary["fallback_rate"] = summary["fallback_count"] / len(decisions)
        summary["raw_ineligible_count"] = sum(row["raw_ineligible"] for row in decisions)
        summary["references_valid"] = all(row["references_valid"] for row in decisions)
        protected = [row for row in decisions if row["target"] in ["FIX", "ABSTAIN"]]
        summary["protected_cases"] = len(protected)
        summary["protected_delivered_correct"] = sum(row["delivered"] == row["target"] for row in protected)
        timings = sorted(row["seconds"] for row in decisions)
        summary["request_latency_seconds"] = {"median": statistics.median(timings), "p95": timings[min(len(timings) - 1, int(0.95 * len(timings)))], "includes_prompt_prefill": True, "warm_model": True, "includes_tokenization": False, "includes_audit_and_rendering": False}
        per_class = summary["raw"]["by_action"]
        summary["engineering_gate_passed"] = partition == "test" and limit is None and summary["raw"]["agreement"] >= 0.90 and all(item["agreement"] >= 0.80 for item in per_class.values()) and summary["references_valid"] and summary["protected_delivered_correct"] == len(protected)
    return summary, decisions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Omit for rules-only; use a Hub ID or adapted checkpoint path.")
    parser.add_argument("--name", default="rules")
    parser.add_argument("--partition", choices=["validation", "test", "published"], default="test")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    runtime = None
    metadata = {}
    if args.model:
        import psutil
        from small_model.model_runtime import ActionModel, model_metadata
        runtime = ActionModel(args.model, args.device, args.threads, args.revision)
        metadata = model_metadata(runtime)
        # One unlabelled warm-up is excluded from the latency distribution.
        audits = json.loads((ROOT / "data/audits.json").read_text(encoding="utf-8"))
        sample = json.loads((ROOT / f"data/{args.partition}.jsonl").read_text(encoding="utf-8").splitlines()[0])
        runtime.choose(evidence_packet(audits[sample["audit_id"]]), sample["request"], sample["resources"])
    summary, decisions = evaluate(args.partition, runtime, args.limit)
    if runtime:
        memory = psutil.Process().memory_info()
        metadata["process_peak_resident_bytes"] = getattr(memory, "peak_wset", None)
        if metadata["process_peak_resident_bytes"] is None:
            import resource
            metadata["process_peak_resident_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        metadata["process_resident_bytes_after_evaluation"] = memory.rss
        if Path(args.model).is_dir():
            metadata["weight_file_bytes"] = sum(path.stat().st_size for path in Path(args.model).glob("*.safetensors"))
        summary["model_metadata"] = metadata
    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    (output / f"{args.name}_{args.partition}.json").write_text(json.dumps({"summary": summary, "decisions": decisions}, indent=2, allow_nan=False), encoding="utf-8")
    compact = {key: value for key, value in summary.items() if key not in ["fixed", "rules", "raw", "delivered"]}
    for key in ["fixed", "rules", "raw", "delivered"]:
        if key in summary:
            compact[key] = {field: summary[key][field] for field in ["n", "correct", "agreement"]}
    print(json.dumps(compact, indent=2), flush=True)


if __name__ == "__main__":
    main()
