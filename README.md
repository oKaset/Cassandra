![Python](https://img.shields.io/badge/python-3.10+-blue)
![Accuracy](https://img.shields.io/badge/accuracy-66.13%25-green)
![F1 ponderado](https://img.shields.io/badge/F1_ponderado-64.90%25-green)
[![Demonstração](https://img.shields.io/badge/demo-live-brightgreen)](https://okaset.github.io/Cassandra/)

# CASSANDRA Oracle Engine

CASSANDRA é uma plataforma de inteligência territorial que cruza dados demográficos, indicadores económicos e memória digital preservada pelo Arquivo.pt para classificar os 308 municípios portugueses em níveis de risco demográfico-digital.

## Demonstração pública

🔗 [https://okaset.github.io/Cassandra/](https://okaset.github.io/Cassandra/)

---

## Ideia central

O Arquivo.pt é usado como **fonte analítica primária**: os seus registos permitem transformar memória web preservada em variáveis computacionais de presença, densidade e persistência digital territorial.

Estas variáveis são incorporadas directamente no modelo preditivo. A sua remoção — documentada através de um estudo de ablação controlado — produz uma degradação mensurável no desempenho. O Arquivo.pt não é, portanto, uma ilustração: é uma fonte de sinal territorial.

---

## Cadeia de evidência

```text
Registos Arquivo.pt
  → variáveis digitais (Total_Arquivo_Captures, capture_density, digital_decay_rate como variável temporal legada)
  → modelo XGBoost com Optuna + SMOTE
  → classificação territorial (Tier 1 a Tier 4)
  → estudo de ablação (impacto da remoção das variáveis Arquivo.pt)
```

O site público inclui a secção **"A PROVA // DA CAPTURA À CLASSIFICAÇÃO"**, que expõe a cadeia de evidência completa para auditoria pelos júris.

---

## Variáveis principais do modelo

| Variável | Tipo | Descrição |
|---|---|---|
| `Var% 2001→2011` | Demográfica | Variação populacional intercensitária |
| `Env. 2001` | Demográfica | Índice de envelhecimento em 2001 |
| `Pop. 2011` | Demográfica | População residente em 2011 |
| `IEI_Score` | Índice composto | Índice de Exposição e Isolamento territorial |
| `is_coastal` | Geográfica | Indicador de município costeiro |
| `Total_Arquivo_Captures` | **Arquivo.pt** | Capturas usadas pelo modelo (valor de entrada do modelo) |
| `capture_density` | **Arquivo.pt** | `Total_Arquivo_Captures` / Pop. 2021 |
| `digital_decay_rate` | **Arquivo.pt** | Variável legada importada de `Media_Dias_Entre_Capturas` |

> **Nota:** `Total_Arquivo_Captures` é o valor de entrada do modelo, não um total histórico completo. O `checkpoint_cdx_record_count` é evidência de checkpoint capeada a 5 000 registos por domínio. São grandezas distintas.
>
> Para reduzir a dependência de uma variável temporal legada, o projecto inclui um Arquivo Core Robustness Check, que isola as variáveis Arquivo.pt com fórmula totalmente auditável: `Total_Arquivo_Captures` e `capture_density`. A `digital_decay_rate` é mantida com proveniência documentada, mas com limitação assumida quanto à fórmula original.

---

## Modelo

- **Algoritmo:** XGBoost (`XGBClassifier`)
- **Optimização de hiperparâmetros:** Optuna (pesquisa bayesiana)
- **Validação cruzada:** StratifiedKFold 5-fold
- **Balanceamento de classes:** SMOTE aplicado exclusivamente ao conjunto de treino (nunca ao conjunto de teste)
- **Explicabilidade:** SHAP values por município e por variável
- **Tiers de risco:** 4 classes (Tier 1 — Resiliência → Tier 4 — Risco Crítico)

---

## Métricas confirmadas

### Com Arquivo.pt

| Métrica | Valor |
|---|---|
| Accuracy | 66.13% |
| F1 ponderado | 64.90% |

### Sem Arquivo.pt (ablação)

| Métrica | Valor |
|---|---|
| Accuracy | 58.06% |
| F1 ponderado | 58.19% |

### Impacto da remoção das variáveis Arquivo.pt

| Métrica | Delta |
|---|---|
| Accuracy | −8.06 pp |
| F1 ponderado | −6.71 pp |
| Recall Tier 1 | −18.18 pp |
| Recall Tier 2 | −20.00 pp |
| Recall Tier 3 | +5.00 pp |
| Recall Tier 4 | −6.25 pp |

> O objectivo é enquadrar CASSANDRA como **sistema de apoio à decisão** e demonstrar que a memória digital arquivada contém **sinal territorial mensurável**.

Fontes de métricas públicas: `reports/confirmed_model_metrics.json`, `data/arquivo_ablation_summary.json`, `arquivo_ablation_results.json`.

---

## Evidence Pack

Conjunto de ficheiros auditáveis que documentam a cadeia desde os registos Arquivo.pt até às classificações do modelo:

| Ficheiro | Conteúdo |
|---|---|
| `data/arquivo_evidence_summary.csv` | Resumo de evidência por município |
| `data/arquivo_feature_audit.csv` | Auditoria de variáveis Arquivo.pt por município |
| `data/arquivo_capture_samples.csv` | Amostras de capturas Arquivo.pt |
| `data/arquivo_evidence_pack.json` | Manifesto completo do Evidence Pack |
| `data/arquivo_ablation_summary.json` | Resumo do estudo de ablação por variável |
| `data/arquivo_core_robustness_summary.json` | Robustez secundária das variáveis Arquivo Core |
| `docs/ARQUIVO_EVIDENCE_PACK.md` | Documentação narrativa do Evidence Pack |
| `docs/DIGITAL_DECAY_RATE_PROVENANCE.md` | Proveniência e limitação da variável `digital_decay_rate` |
| `reports/confirmed_model_metrics.json` | Métricas públicas confirmadas |
| `arquivo_ablation_results.json` | Resultados completos do estudo de ablação |

**Distinções importantes:**

- `checkpoint_cdx_record_count` — evidência de checkpoint Arquivo.pt, capeada a 5 000 registos por domínio; não representa o total histórico completo.
- `model_total_arquivo_captures` — valor efectivamente usado pelo modelo como variável de entrada.
- `capture_count_imputed` — marca imputação quando capturas directas não estavam disponíveis.
- checkpoint CDX local — artefacto interno; intencionalmente não exposto no site público.

---

## Casos demonstrativos

Os casos abaixo ilustram a diversidade de padrões captados pelo modelo. Não representam previsões definitivas.

| Município | Classificação | Observação |
|---|---|---|
| **Alcácer do Sal** | Tier 4 — Risco Crítico | Fraca persistência digital aliada a indicadores demográficos de risco elevado |
| **Torres Vedras** | Tier 1 — Resiliência | Continuidade territorial e digital mais sólida |
| **Proença-a-Nova** | Tier 4 — Risco Crítico | Demonstra que um número elevado de capturas não garante automaticamente resiliência territorial |

---

## Estrutura do repositório

```text
ARQUIVOPT2026/
├── README.md
├── AGENTS.md
├── index.html                        ← Site público estático
├── app_cassandra.py                  ← Dashboard Streamlit (uso interno)
├── cassandra_opcao_a.py              ← Pipeline principal de classificação
├── modelo_preditivo_real.py          ← Pipeline preditivo completo
├── arquivo_ablation_results.json     ← Resultados de ablação
├── data/
│   ├── arquivo_evidence_summary.csv
│   ├── arquivo_feature_audit.csv
│   ├── arquivo_capture_samples.csv
│   ├── arquivo_evidence_pack.json
│   ├── arquivo_ablation_summary.json
│   └── arquivo_core_robustness_summary.json
├── docs/
│   ├── ARQUIVO_EVIDENCE_PACK.md
│   └── DIGITAL_DECAY_RATE_PROVENANCE.md
├── reports/
│   └── confirmed_model_metrics.json
├── scripts/
├── assets/
│   └── dashboard_data.js
├── dados_demograficos.csv
├── municipios_dominios.csv
├── municipios.geojson
└── relatorio_produto_cassandra.csv
```

---

## Instalação e execução

```bash
# Criar e activar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install pandas numpy scikit-learn xgboost imbalanced-learn optuna shap

# Pipeline principal de classificação
python cassandra_opcao_a.py

# Sem re-extracção de features
python cassandra_opcao_a.py --skip-extraction

# Comparação sem SMOTE
python cassandra_opcao_a.py --no-smote

# Dashboard Streamlit (uso interno/desenvolvimento)
streamlit run app_cassandra.py
```

---

## Limitações

- A classificação é exploratória e orientada ao apoio à decisão; não substitui análise especializada.
- O checkpoint CDX Arquivo.pt está capeado a 5 000 registos por domínio, não representando o histórico completo de capturas.
- Os URLs de replay são gerados programaticamente e não foram verificados de forma independente.
- A variável `digital_decay_rate` é importada da coluna `Media_Dias_Entre_Capturas`; a fórmula de derivação original não é completamente recuperável.
- Para reduzir a dependência de uma variável temporal legada, o projecto inclui um Arquivo Core Robustness Check, que isola as variáveis Arquivo.pt com fórmula totalmente auditável: `Total_Arquivo_Captures` e `capture_density`. A `digital_decay_rate` é mantida com proveniência documentada, mas com limitação assumida quanto à fórmula original.
- O modelo deve apoiar a análise territorial, não substituir o julgamento humano.

---

## Licença

MIT
