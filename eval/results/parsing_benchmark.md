| Metric | Regex baseline | LLM (qwen2.5:7b) |
|---|---|---|
| Questions (complete, of which hard / all) | 35, 9 / 47 | 35, 9 / 47 |
| Accuracy: place | 83% | 100% |
| Accuracy: season | 100% | 100% |
| Accuracy: years | 100% | 100% |
| Accuracy: index | 100% | 100% |
| Accuracy: distance | 97% | 94% |
| **Exact match (all fields)** | **80%** | **94%** |
| Exact match, free phrasing (hard) | 33% | 89% |
| Exact match, English | 71% | 95% |
| Exact match, French | 93% | 93% |
| Asks for the right missing info (missing) | 75% | 100% |
| Rejects invalid requests (invalid) | 75% | 100% |
| **Correct decision, all questions** | **81%** | **100%** |
| Model errors | 0 | 0 |
| Mean time per question | 0.00 s | 12.85 s |
