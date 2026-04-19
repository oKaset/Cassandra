"""ArquivoPT2026 — List all 308 domains."""

import sys
import pandas as pd

METRICS_FILE = "metricas_iei_completo.csv"
OUTPUT_FILE  = "lista_308_dominios.txt"

try:
    df = pd.read_csv(METRICS_FILE)
except FileNotFoundError:
    print(f"ERROR: {METRICS_FILE} not found.")
    sys.exit(1)

df = df.sort_values("Município", key=lambda s: s.str.lower()).reset_index(drop=True)

lines = []
for i, row in df.iterrows():
    line = f"[{i+1:03d}] {row['Município']:<32} → {row['Domain']}"
    lines.append(line)
    print(line)

with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")

print()
print(f"Total: {len(df)} municipalities")
print(f"Saved → {OUTPUT_FILE}")
