# Model-comparison evaluation set

The original Tier 2 cases C1-C3 test mechanism attribution on ETTh1. The
additional cases broaden the skill without requiring new training runs:

| Case | Capability under test | Evidence source |
| --- | --- | --- |
| `tier2-c1b` | Opaque C1 intervention discovery | Hard-linked C1 artifacts |
| `tier2-c2b` | Opaque multi-mechanism and horizon reasoning | C1-C3, Tier 1, and pl720 artifacts |
| `tier2-c3b` | Opaque factor attribution | C3 factor artifacts |
| `tier2-c4` | Horizon transfer versus pooled composition shift | pl96, pl336, pl720 |
| `tier2-c5` | Multi-model portfolio, ensemble, and selector uncertainty | Seven Weather baselines |
| `tier2-c6` | Architecture versus optimization, including unresolved causes | Weather TSMixer/TiDE + HW1 |
| `tier2-c7` | Cross-domain conditional generalization | ETTh1 and Weather baselines |
| `holdout/HX1` | Blind cross-domain transfer gate | ETTh1 and Weather baselines |

The new measurement scripts are read-only recomputation tools. Their generated
JSON files are the numeric receipts used by the corresponding gold cases. No
case requires web search: general architecture knowledge is a prior, while
configs, predictions, slices, and interventions are the evidence.

Blind packages deliberately expose only opaque artifact IDs. They contain
hard-linked `pred.npy`, `true.npy`, and `config.json` files, not duplicate model
checkpoints.
