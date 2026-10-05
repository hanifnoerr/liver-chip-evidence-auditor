"""Score a short action code with a causal language model on CPU or CUDA."""

from pathlib import Path
import copy
import time

from small_model.planner import ACTION_CODES, prompt_messages

BASE_MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
BASE_REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
CACHE = Path(__file__).resolve().parent / "model_cache"


class ActionModel:
    def __init__(self, model_path=BASE_MODEL, device="cpu", threads=4, revision=None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        if revision is None and model_path == BASE_MODEL:
            revision = BASE_REVISION
        torch.set_num_threads(threads)
        self.device = device
        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, revision=revision, cache_dir=CACHE)
        self.model = AutoModelForCausalLM.from_pretrained(model_path, revision=revision, cache_dir=CACHE)
        self.model.to(device).eval()
        self.load_seconds = time.perf_counter() - started
        self.model_path = model_path
        self.revision = getattr(self.model.config, "_commit_hash", None)
        training_file = Path(model_path) / "training_record.json"
        if training_file.is_file():
            import json
            self.revision = json.loads(training_file.read_text(encoding="utf-8"))["resolved_base_revision"]
        self.parameters = sum(parameter.numel() for parameter in self.model.parameters())
        self.weight_dir = Path(model_path)
        if not self.weight_dir.is_dir():
            from huggingface_hub import snapshot_download
            self.weight_dir = Path(snapshot_download(model_path, revision=self.revision, cache_dir=CACHE, local_files_only=True))
        self.code_ids = {}
        for code in ACTION_CODES:
            self.code_ids[code] = self.tokenizer.encode(code, add_special_tokens=False)

    def choose(self, packet, request, resources):
        torch = self.torch
        messages = prompt_messages(packet, request, resources)
        inputs = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(self.device)
        started = time.perf_counter()
        scores = {}
        with torch.inference_mode():
            prefix = self.model(inputs, use_cache=True)
            first_logits = prefix.logits[0, -1]
            # Reuse the numerical-evidence prefix; each short code has its own cache branch.
            for code, token_ids in self.code_ids.items():
                logits = first_logits
                cache = copy.deepcopy(prefix.past_key_values) if len(token_ids) > 1 else None
                score = 0.0
                for index, token_id in enumerate(token_ids):
                    score += torch.log_softmax(logits.float(), dim=-1)[token_id].item()
                    if index < len(token_ids) - 1:
                        next_input = torch.tensor([[token_id]], device=self.device)
                        output = self.model(next_input, past_key_values=cache, use_cache=True)
                        logits = output.logits[0, -1]
                        cache = output.past_key_values
                scores[code] = score / len(token_ids)
        if self.device == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        choice = max(scores, key=scores.get)
        return choice, {"scores": scores, "seconds": elapsed, "prompt_tokens": inputs.shape[1]}


def model_metadata(runtime):
    import platform
    import psutil
    import transformers

    return {
        "model": str(runtime.model_path), "resolved_revision": runtime.revision,
        "parameters": runtime.parameters, "device": runtime.device,
        "weight_dtype": str(next(runtime.model.parameters()).dtype),
        "threads": runtime.torch.get_num_threads(), "load_seconds": runtime.load_seconds,
        "python": platform.python_version(), "torch": runtime.torch.__version__,
        "transformers": transformers.__version__, "platform": platform.platform(),
        "processor": platform.processor(), "ram_bytes": psutil.virtual_memory().total,
        "weight_file_bytes": sum(path.stat().st_size for path in runtime.weight_dir.glob("*.safetensors")),
    }
