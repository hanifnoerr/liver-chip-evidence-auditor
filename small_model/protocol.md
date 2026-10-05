# Small-model action-selection experiment

Frozen before dataset generation and model inference on 5 October 2026.

The task is to choose a follow-up action for a day-three albumin evidence audit, given its measured sensitivity, the researcher's request and explicit resource constraints. The numerical auditor is unchanged. The language model selects an action class; Python supplies the source-specific action text, measurements and references. This experiment does not test generated scientific explanations, optimal experimental design or biological benefit.

Start with `HuggingFaceTB/SmolLM2-135M-Instruct`. Compare the untuned checkpoint with supervised adaptation. If its held-out quality is inadequate, 360M is a subsequent experiment, not an already selected winner. CPU inference is the initial deployment target. A PC benchmark is not a Raspberry Pi or phone benchmark.

The downloaded base revision is `12fd25f77366fa6b3b4b768ec3050bf629380bac`, with 134,515,008 parameters and 269,060,552 weight-file bytes. It is pinned before adaptation. The runtime check compares cached completion likelihoods with full forwards; it does not evaluate biological validity. The PC has an Intel Core Ultra 5 125H and an RTX 3050 6 GB GPU. Local GPU adaptation can use the same fixed recipe as the prepared Colab notebook; CPU deployment remains the target.

## Data and separation

Use fresh simulations from the existing auditor generator. Training uses Hill responses with clean, random-missing, response-dependent-missing, truncated-range, singleton and influential-reading conditions. Validation uses new experiments in those same families. Test has new in-family experiments plus held-out piecewise responses and the non-monotonic/run-shift fault families. Each experiment and all its requests stay in one partition. Six published compounds are an additional demonstration set, excluded from training and validation. Real demonstrations have policy labels, not scientist-adjudicated ground truth.

Seeds are 20261005, 20261006 and 20261007. Generate 96 training experiments, 24 validation experiments and 48 test experiments. Every experiment has seven requests: record review, one repeat, missing-record recovery, finite-crossing estimation, bounded reporting, an unsupported clinical/exclusion request and curve-model review. Request wording differs by partition. Include blocked-input variants, each grouped with its parent experiment. Store provenance and split membership. Synthetic records do not add independent real chips.

Before any model inference or training, the initial six-request generation was inspected for action coverage. It produced no COMPARE targets in validation/test. A seventh explicit curve-review request was added before freezing the model benchmark. Both the policy and lexical rules recognise this goal. No model results informed this revision. Templates are authored for this prototype; performance on them is not a naturalistic user study.

Targets come from an explicit heuristic policy. They are policy-distillation labels, not expert or biological labels. The policy prioritises resolving blocked input, declining unsupported requests, then actions relevant to the requested goal and feasible resources. It distinguishes influential readings, missingness that changes the conclusion, model disagreement and loss of dose coverage. It makes no claim to maximise information gain. The reference policy with known intent is an upper bound by construction; the deployable rules baseline infers intent from the request text.

## Comparisons and reporting

Compare a fixed action order, a request-aware rules planner, the untuned language model and the adapted language model. Report raw policy agreement, delivered policy agreement after eligibility checks, raw ineligible-action rate, fallback rate and agreement by action class and response family. Record every choice, source references, prompt length and inference time. Do not present fallback-corrected performance as the language model's own accuracy. Check that the renderer cites only records/scenarios in the supplied audit. Numerical text is copied from Python, so this is not a test of LLM numerical reasoning.

Split by experiment before adaptation. Select checkpoints on validation only. Keep test and published cases out of training. Freeze any revised policy or prompts before a new held-out evaluation. Quantisation needs a separate evaluation because it may change action choices.

## Initial release gate

The model is experimental until raw agreement reaches 90% overall and at least 80% in each represented action class on the untouched test set, no blocked-input/unsupported-request case receives a forbidden delivered action, and all delivered source/scenario references are valid. These are engineering gates, not evidence of scientific validity. Report sample counts. Compare with the request-aware rules baseline, including where that baseline is better. Passing the gate alone does not demonstrate a benefit over rules.

Measure CPU model-load time, warm median/p95 request latency, process peak resident memory and weight-file size. Keep model-load time separate from request latency; document CPU, RAM, thread count and model revision. No edge-performance claim is permitted before a benchmark on the named edge device.

Timing clarification: the recorded `request_latency_seconds` is model scoring time, including prompt prefill and completion-code scoring. It excludes tokenisation, numerical auditing and action rendering, so it is not end-to-end HTTP latency. Model-load time excludes Python package import and uses locally cached weights. This clarification does not change the frozen policy, data, training recipe or gate.

The prepared Colab notebook performs full quality evaluation on its GPU and a limited CPU smoke benchmark on the first 14 published requests. That limited run cannot pass the full test gate and is labelled separately. A returned checkpoint must still be benchmarked on this PC, then on any selected edge device. The checkpoint is selected by lowest validation assistant-token loss over three fixed training epochs.
