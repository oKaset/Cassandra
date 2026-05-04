![Python](https://img.shields.io/badge/python-3.10+-blue)
![F1 Score](https://img.shields.io/badge/F1--score-0.87-green)
[![Live Site](https://img.shields.io/badge/demo-live-brightgreen)](https://okaset.github.io/Cassandra/)

# CASSANDRA

Predict digital decay risk for Portugal's 308 municipalities using Arquivo.pt web archive evidence and an XGBoost classifier.

## What it does

CASSANDRA estimates digital decay risk across Portugal's 308 municipalities. It uses 20+ years of Arquivo.pt web archive captures, combines them with municipal indicators, and produces a Digital Exposure Index (IEI) with four risk tiers.

The public dashboard is available at https://okaset.github.io/Cassandra/.

## How it works

The pipeline follows a data-to-output workflow:

```text
Arquivo.pt captures + demographic data
  -> feature extraction
  -> XGBoost classification
  -> Digital Exposure Index (IEI) and risk tier assignment
```

Key extracted features include `site_mortality_rate`, `capture_acceleration`, and `last_capture_gap_days`.

The IEI output maps each municipality to one of four tiers:

```text
TIER 1 - Resiliência
TIER 2 - Estagnação
TIER 3 - Risco de Fuga
TIER 4 - Profecia CASSANDRA
```

## Key finding

CASSANDRA identifies 83 municipalities in `TIER 4 - Profecia CASSANDRA`, the critical risk tier. The distribution suggests that digital decay risk is systemic rather than limited to isolated municipal websites.

## Model performance

The predictive model is an XGBoost classifier validated with an F1 score of 0.87.

Methodology:

- 5-fold stratified cross-validation
- Optuna hyperparameter tuning
- SMOTE applied to training folds for class balancing

## Installation & usage

Create and activate a Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the main Python dependencies:

```bash
pip install pandas numpy scikit-learn xgboost imbalanced-learn optuna
```

Run the main CASSANDRA evaluation pipeline:

```bash
python cassandra_opcao_a.py
```

Run against an existing feature matrix without re-running extraction:

```bash
python cassandra_opcao_a.py --skip-extraction
```

Run a comparison without SMOTE:

```bash
python cassandra_opcao_a.py --no-smote
```

Optional related scripts:

```bash
python modelo_preditivo_real.py
streamlit run app_cassandra.py
```

## Project structure

```text
CASSANDRA/
├── README.md
├── cassandra_opcao_a.py
├── modelo_preditivo_real.py
├── app_cassandra.py
├── index.html
├── relatorio_produto_cassandra.csv
├── feature_matrix_v2.csv
├── dados_demograficos.csv
├── municipios_dominios.csv
├── municipios.geojson
├── data/
│   └── arquivo_temporal_features.csv
├── reports/
│   └── model_metrics.json
└── assets/
    └── dashboard_data.js
```

## Data sources

CASSANDRA uses the Arquivo.pt CDX API as its primary source for archived web capture data. The model also incorporates demographic data for Portuguese municipalities.

## License

MIT
