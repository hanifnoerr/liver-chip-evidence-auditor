"""Supervised adaptation with assistant-code loss and validation-only selection."""

from contextlib import nullcontext
from pathlib import Path
import argparse
import json
import random
import time

ROOT = Path(__file__).resolve().parent


def encode_examples(path, tokenizer):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    encoded = []
    for row in rows:
        prefix = tokenizer.apply_chat_template(row["messages"], add_generation_prompt=True)
        completion = tokenizer.encode(row["target"] + tokenizer.eos_token, add_special_tokens=False)
        input_ids = prefix + completion
        if len(input_ids) > 1024:
            raise ValueError("Prompt exceeds the frozen training context: " + row["example_id"])
        labels = [-100] * len(prefix) + completion
        encoded.append({"input_ids": input_ids, "labels": labels})
    return encoded


def main():
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from small_model.model_runtime import BASE_MODEL, BASE_REVISION, CACHE

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--output", default=str(ROOT / "checkpoints/smollm2-135m-policy"))
    args = parser.parse_args()
    if args.revision is None and args.base_model == BASE_MODEL:
        args.revision = BASE_REVISION
    if args.epochs < 1 or args.batch_size < 1:
        raise ValueError("Epochs and batch size must be positive.")
    output = Path(args.output)
    if (output / "config.json").exists():
        raise ValueError("The output already contains a model. Choose a new --output path to preserve it.")
    random.seed(20261005)
    torch.manual_seed(20261005)
    torch.set_num_threads(args.threads)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, revision=args.revision, cache_dir=CACHE)
    tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.base_model, revision=args.revision, cache_dir=CACHE).to(args.device)
    base_revision = getattr(model.config, "_commit_hash", None)
    training_rows = encode_examples(ROOT / "data/train.jsonl", tokenizer)
    validation_rows = encode_examples(ROOT / "data/validation.jsonl", tokenizer)

    def pad_batch(rows):
        length = max(len(row["input_ids"]) for row in rows)
        inputs = []
        masks = []
        labels = []
        for row in rows:
            padding = length - len(row["input_ids"])
            inputs.append(row["input_ids"] + [tokenizer.pad_token_id] * padding)
            masks.append([1] * len(row["input_ids"]) + [0] * padding)
            labels.append(row["labels"] + [-100] * padding)
        return {"input_ids": torch.tensor(inputs), "attention_mask": torch.tensor(masks), "labels": torch.tensor(labels)}

    training_loader = DataLoader(training_rows, batch_size=args.batch_size, shuffle=True, collate_fn=pad_batch)
    validation_loader = DataLoader(validation_rows, batch_size=args.batch_size, collate_fn=pad_batch)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    use_bfloat = args.device == "cuda" and torch.cuda.is_bf16_supported()
    history = []
    best_loss = float("inf")
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    for epoch in range(args.epochs):
        model.train()
        train_total = train_tokens = 0
        for step, batch in enumerate(training_loader):
            batch = {key: tensor.to(args.device) for key, tensor in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            precision = torch.autocast("cuda", dtype=torch.bfloat16) if use_bfloat else nullcontext()
            with precision:
                loss = model(**batch, use_cache=False).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            tokens = (batch["labels"][:, 1:] != -100).sum().item()
            train_total += loss.item() * tokens
            train_tokens += tokens
            if step % 20 == 0:
                print(f"epoch {epoch + 1}, step {step + 1}/{len(training_loader)}, loss {loss.item():.4f}", flush=True)
        model.eval()
        validation_total = validation_tokens = 0
        with torch.inference_mode():
            for batch in validation_loader:
                batch = {key: tensor.to(args.device) for key, tensor in batch.items()}
                precision = torch.autocast("cuda", dtype=torch.bfloat16) if use_bfloat else nullcontext()
                with precision:
                    loss = model(**batch, use_cache=False).loss
                tokens = (batch["labels"][:, 1:] != -100).sum().item()
                validation_total += loss.item() * tokens
                validation_tokens += tokens
        validation_loss = validation_total / validation_tokens
        history.append({"epoch": epoch + 1, "train_assistant_token_loss": train_total / train_tokens, "validation_assistant_token_loss": validation_loss})
        print(history[-1], flush=True)
        if validation_loss < best_loss:
            best_loss = validation_loss
            model.save_pretrained(output)
            tokenizer.save_pretrained(output)
            selected_epoch = epoch + 1
    record = {
        "base_model": args.base_model, "resolved_base_revision": base_revision,
        "seed": 20261005, "device": args.device, "epochs": args.epochs,
        "batch_size": args.batch_size, "learning_rate": args.learning_rate,
        "weight_decay": 0.01, "gradient_clip_norm": 1.0,
        "training_examples": len(training_rows), "validation_examples": len(validation_rows),
        "selected_epoch": selected_epoch, "selection": "lowest_validation_assistant_token_loss",
        "history": history, "training_seconds": time.perf_counter() - started,
        "torch": torch.__version__, "mixed_precision_bfloat16": use_bfloat,
        "gpu_name": torch.cuda.get_device_name(0) if args.device == "cuda" else None,
        "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated() if args.device == "cuda" else None,
        "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved() if args.device == "cuda" else None,
        "label_source": "heuristic_policy_not_biological_truth", "test_used_for_selection": False,
    }
    (output / "training_record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("Saved selected model:", output, flush=True)


if __name__ == "__main__":
    main()
