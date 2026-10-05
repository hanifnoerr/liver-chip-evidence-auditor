# Compact liver-chip action planner

The local SmolLM2-135M-Instruct planner selects an action class from calculated evidence, a researcher request and resource limits. Python checks eligibility, applies a rules fallback for ineligible proposals, and supplies the source-specific evidence text. Measurements, numerical results, named conditions and citations come from the auditor. The model is available as an experimental option alongside the default rules baseline.

## Use the checkpoint

Extract the code package and checkpoint ZIP into the same project root, then run:

```text
conda env create -f small_model/environment.yml
conda activate ai4s-liver-slm
python demo.py --model small_model/checkpoints/smollm2-135m-policy --threads 4
```

Open the printed address, select Next action, then choose **Small language model · experimental**. Set your goal and resources and select **Find a next action**.

## Evaluation, 5 October 2026

The 134,515,008-parameter SmolLM2 checkpoint was adapted using PyTorch 2.8.0+cu126, Transformers 4.57.1 and Psutil 7.1.0. Training ran on the RTX 3050 6 GB laptop GPU for 334.34 seconds. Three epochs were completed; epoch 2 was selected by lowest validation assistant-token loss (0.01127). Test cases did not select the checkpoint. All 728 training sequences fit the 1,024-token limit; the longest is 338 tokens. Adapted cached action-code scores agree with full forwards within 0.000016.

The untuned model selected REPEAT for a published Clozapine request with a zero-repeat budget. Eligibility checks retained the raw choice and returned an admissible fallback.

The experiment has 728 training requests from 96 simulated experiments, 182 validation requests from 24 experiments and 364 test requests from 48 experiments. Duplicate-input variants stay with their parent experiment. The six published compounds provide 42 additional demonstration requests. Experiment groups do not cross partitions. All 1,316 target actions and rendered source/scenario references passed the local checks.

The following results measure agreement with our heuristic policy, not expert judgments.

| Planner | Raw agreement, test | Delivered agreement after guard |
|---|---:|---:|
| Fixed action order | 237/364 (65.1%) | Not evaluated |
| Request-aware rules | 364/364 (100%) | No correction needed |
| Untuned 135M model | 72/364 (19.8%) | 144/364 (39.6%) |
| Adapted 135M model | 337/364 (92.6%) | 361/364 (99.2%) |

The scope guard corrects all 24 tested unsupported-request errors. All 76 blocked/unsupported test cases receive the correct delivered action, and every rendered source/scenario reference is valid. Three delivered discrepancies remain: two model-review requests select INSPECT instead of COMPARE, and one finite-crossing request selects RECOVER instead of REPORT. Raw ABSTAIN agreement is 24/48 (50%) and COMPARE is 0/2, leaving the predefined per-class gate unmet. No raw action is resource-ineligible; eligibility alone does not establish the right priority.

On the six published compounds, the adapted model matches 41/42 authored policy targets (97.6%), versus 42/42 for rules and 26/42 for fixed order. Pioglitazone's finite-crossing request returns RECOVER where the policy prioritises REPEAT. These demonstrations are excluded from training but are not independent biological validation.

Templates and policy were authored together, and rules match all authored test labels. This benchmark establishes policy agreement and the operation of the checks; an advantage over rules requires separate evaluation. COMPARE and EXTEND have only 2 and 4 test targets, respectively. The 364 requests share 48 parent experiments. The next stage will collect independently written, expert-reviewed liver-chip cases to train and compare more capable models using fresh held-out experiment groups and the same numerical and resource checks. Rules remain the default baseline during this evaluation.

On an Intel Core Ultra 5 125H PC with 31.7 GiB RAM and four Torch CPU threads, adapted model scoring takes a warm median of 1.33 seconds and p95 of 2.29 seconds on the full test. Scoring includes prompt prefill and action-code likelihoods, excluding tokenisation, numerical auditing and rendering. Cached model loading takes 1.17 seconds, excluding package imports. Process peak resident memory is 1.58 GiB; FP32 weight files occupy 538,090,408 bytes (513.2 MiB). The untuned run used the CPU Torch build, whereas the adapted run used the CUDA-capable build on CPU; these timings do not isolate an adaptation speed effect. These hardware results cover the tested PC. Quantisation and benchmarks on named edge devices are planned deployment steps.

Results: `results/untuned_pc_test.json`, `results/adapted_pc_test.json`, `results/adapted_pc_published.json`, `results/training_record.json` and `results/adapted_runtime_checks.json`. The editable method figure is `framework.svg`; `framework_notes.md` maps it to the code.

## Optional Colab L4 reproduction

1. Open `output/jupyter-notebook/liver_chip_slm_colab.ipynb` in Colab and select the L4 GPU runtime.
2. Run the first cell and upload `small_model/small_model_colab.zip` when its uploader appears.
3. Run the notebook in order. It evaluates the untuned checkpoint, records its revision, trains for three epochs using validation-only checkpoint selection, evaluates held-out requests and runs a limited CPU smoke benchmark.
4. Download `liver_chip_slm_result.zip` from the last cell. Preserve it before ending the runtime. Its weights and evaluation results can then be brought back to this workspace.

The notebook is scaffolded and its code cells compile. It has not been executed on Colab. The CPU smoke benchmark measures Colab's CPU and cannot establish performance on this PC or a target edge device.

## Reproduce the local experiment

From the repository root, in Anaconda Prompt:

```text
conda activate ai4s-liver-slm
python -m pip install -r small_model/requirements.txt
python -m small_model.check_planner
python -m small_model.evaluate --model HuggingFaceTB/SmolLM2-135M-Instruct --name untuned --partition test --device cpu
```

To reproduce the generated data, use the original auditor environment and `python -m small_model.build_dataset`. This needs the root auditor sources and original saved results, not the standalone Colab package.

To train again, choose a new output directory so the selected checkpoint is preserved. Use the frozen recipe: `python -m small_model.train --device cuda --epochs 3 --batch-size 8 --learning-rate 0.00005 --output small_model/checkpoints/reproduction`. To repeat the completed adapted CPU evaluation:

```text
python -m small_model.evaluate --model small_model/checkpoints/smollm2-135m-policy --name adapted_pc --partition test --device cpu --threads 4
```

## Interpretation and further validation

The language-model runtime scores the eight short action-code completions by mean token log likelihood, reusing the prompt cache. Scores are not calibrated confidence. Raw model choices, eligibility failures and fallback-corrected choices are recorded separately. Selection of the first influential condition within an action class is deterministic, not learned or optimal.

Read `protocol.md` before running. The engineering gate is fixed in advance. Even a passing model would demonstrate policy distillation on authored requests, not improved scientific decisions. A subsequent benchmark needs independently written researcher requests, scientist-adjudicated actions and comparison with a strong request-aware rules system. Model-size choice should use validation; changing models after inspecting test results requires a new held-out evaluation.

Base model and paper: [SmolLM2-135M-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct), [SmolLM2 paper](https://arxiv.org/abs/2502.02737). The model has Apache 2.0 licensing. Published evidence derives from Ewart et al., DOI [10.1038/s43856-022-00209-1](https://doi.org/10.1038/s43856-022-00209-1); see `NOTICE.md` for source attribution and CC BY 4.0 conditions. The repository's MIT code licence remains separate.
