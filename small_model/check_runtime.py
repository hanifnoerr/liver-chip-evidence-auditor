"""Verify cached action scores against full teacher-forced model forwards."""

from pathlib import Path
import argparse
import json

from small_model.model_runtime import ActionModel, BASE_MODEL, model_metadata
from small_model.planner import evidence_packet, prompt_messages
from small_model.train import encode_examples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=BASE_MODEL)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--name", default="runtime_checks")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    runtime = ActionModel(args.model, args.device)
    torch = runtime.torch
    audits = json.loads((root / "data/audits.json").read_text(encoding="utf-8"))
    example = json.loads((root / "data/published.jsonl").read_text(encoding="utf-8").splitlines()[0])
    packet = evidence_packet(audits[example["audit_id"]])
    choice, details = runtime.choose(packet, example["request"], example["resources"])
    messages = prompt_messages(packet, example["request"], example["resources"])
    prefix = runtime.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(args.device)
    differences = {}
    with torch.inference_mode():
        for code, token_ids in runtime.code_ids.items():
            suffix = torch.tensor([token_ids], device=args.device)
            logits = runtime.model(torch.cat([prefix, suffix], dim=1), use_cache=False).logits[0]
            score = 0.0
            for index, token_id in enumerate(token_ids):
                position = prefix.shape[1] - 1 + index
                score += torch.log_softmax(logits[position].float(), dim=-1)[token_id].item()
            full_score = score / len(token_ids)
            differences[code] = abs(full_score - details["scores"][code])
    assert max(differences.values()) < 0.001, differences
    rows = encode_examples(root / "data/train.jsonl", runtime.tokenizer)
    for row in rows:
        first_target = next(index for index, label in enumerate(row["labels"]) if label != -100)
        assert all(label == -100 for label in row["labels"][:first_target])
        assert row["labels"][first_target:] == row["input_ids"][first_target:]
    result = {"model_metadata": model_metadata(runtime), "example_id": example["example_id"], "raw_action": choice, "inference": details, "cached_vs_full_max_absolute_difference": max(differences.values()), "training_examples_encoded": len(rows), "longest_training_sequence": max(len(row["input_ids"]) for row in rows), "assistant_only_labels_checked": True}
    (root / f"results/{args.name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
