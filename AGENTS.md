# AGENTS.md

## Project

CASSANDRA Oracle Engine is a static HTML/Tailwind project for Prémio Arquivo.pt 2026.

## Non-negotiable rules

1. Never fabricate data.
   - Do not invent Arquivo.pt links, timestamps, captures, SHAP values, probabilities, model outputs, formulas, municipality values, or metrics.
   - If data is missing, mark it explicitly as missing.

2. Preserve the current stack.
   - Static HTML.
   - Tailwind CSS.
   - No React, Vue, Svelte, Next.js, backend, database, or framework migration.
   - No localStorage.

3. Public Portuguese copy must be PT-PT only.

4. Confirmed public model metrics:
   - With Arquivo.pt: 66.13% accuracy, 64.90% weighted F1.
   - Without Arquivo.pt: 58.06% accuracy, 58.19% weighted F1.
   - Accuracy delta: -8.06 percentage points.
   - Weighted F1 delta: -6.71 percentage points.
   - Tier 1 recall delta: -18.18 percentage points.
   - Tier 2 recall delta: -20.00 percentage points.
   - Tier 3 recall delta: +5.00 percentage points.
   - Tier 4 recall delta: -6.25 percentage points.

5. Arquivo.pt evidence rules:
   - Distinguish checkpoint CDX records from model input values.
   - Do not present checkpoint_cdx_record_count as a complete historical total.
   - Do not expose or link to cdx_checkpoint.json.
   - Always distinguish raw/checkpoint evidence, model values, imputation, and evidence quality.

6. Public framing:
   - Present CASSANDRA as a decision-support and territorial intelligence tool.
   - Do not present it as an infallible oracle.
   - Avoid public-facing “Profecia CASSANDRA”.
   - Prefer “Tier 4 — Risco Crítico” and “classificação de risco”.

7. Before changing public UI:
   - Use validated Evidence Pack files.
   - Do not modify raw/source data.
   - Do not alter Evidence Pack schemas unless explicitly requested.

8. After every task, report:
   - files changed;
   - assumptions made;
   - validation performed;
   - missing data or blockers.
