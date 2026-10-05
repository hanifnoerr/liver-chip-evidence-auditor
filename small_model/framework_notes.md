# Figure verification

The editable `framework.svg` describes the optional action model, separate from the numerical framework at the repository root.

| Operation | Implemented computation |
|---|---|
| Numerical audit | `auditor.analyse_evidence` fits conventional models and calculates finite sensitivity scenarios from original records. |
| Evidence summary | `planner.evidence_packet` and `prompt_messages` pass conclusion state, dose range, changed-scenario counts, concern counts, request, resources and allowed codes. Full source cards are not model inputs. |
| Adaptation | `train.encode_examples` masks the prompt loss; `train.main` adapts all model parameters using assistant-code and EOS loss. The smallest validation loss selects the checkpoint. |
| Code scoring | `model_runtime.ActionModel.choose` reuses prompt KV state and selects the maximum mean token log likelihood over eight action codes. Scores exclude EOS and are not calibrated confidence. |
| Guard | `planner.guard_action` checks eligibility, blocked input and supported lexical request conditions. A forbidden code falls back to request-aware rules. This is not a proof that arbitrary wording is safe. |
| Rendering | `planner.render_action` copies the first relevant existing card for the selected class, including source/scenario references. The model does not learn which dose is optimal. |

Example walk-through: the published Clozapine record-review request has no repeat budget. Its summary contains an influential condition. The adapted checkpoint returns INSPECT, the guard permits it, and Python supplies the existing ALBUMIN!C12 influence card at 300 times unbound Cmax, including the original 69.68% value. The source value reaches the output through the numerical cards, not through model-generated text.

The dashed arrow assigns the selected adapted parameters to inference. Solid arrows carry inputs or outputs. There are no generated parameter matrices, adapters or biological labels in this implementation. Test and published cases do not enter adaptation or checkpoint selection.
