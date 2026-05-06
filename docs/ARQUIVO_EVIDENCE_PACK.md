# Pacote de Evidências Arquivo.pt — CASSANDRA
## Documento para Auditoria por Júri

**Gerado em:** 2026-05-06T01:33:23.049770+00:00
**Fonte de métricas confirmadas do modelo completo:** `reports/model_metrics.json`

---

## 1. O que contém o checkpoint CDX local?

O ficheiro local `cdx_checkpoint.json` contém registos CDX extraídos da API pública do Arquivo.pt para domínios municipais portugueses. Cada registo inclui URL, timestamp, MIME type, HTTP status, digest, filename, collection e source.

Este ficheiro não é copiado para a documentação nem publicado como anexo. O checkpoint tem 1,521,598 registos para 308 domínios; 301/308 domínios estão exatamente no limite local de 5000 registos definido por `cassandra_opcao_a.py`.

**Definição crítica:** “checkpoint_cdx_record_count reflects records available in the local capped checkpoint, not a complete historical total of all Arquivo.pt captures.”

**Definição de validade:** “checkpoint_valid_capture_count counts checkpoint records with status 200, 301, 302, or 304.”

---

## 2. Diferença entre checkpoint e variáveis do modelo

| Conceito | Fonte | Significado |
|---|---|---|
| `checkpoint_cdx_record_count` | `cdx_checkpoint.json` local | Número de registos disponíveis no checkpoint local limitado; não é total histórico completo |
| `checkpoint_valid_capture_count` | `cdx_checkpoint.json` local | Registos do checkpoint com status 200, 301, 302 ou 304 |
| `model_total_arquivo_captures` | `relatorio_produto_cassandra.csv` | Valor de `Total_Arquivo_Captures` usado pelo modelo |
| `capture_count_imputed` | derivado | `yes` quando o modelo usou o valor mediano (628) em vez do valor bruto da fase 2 |

Os campos do checkpoint são evidência de proveniência local. Não são apresentados como valores de entrada do modelo.

---

## 3. Como é calculado `Total_Arquivo_Captures`?

O valor de fase 2 vem de `extrator_fase2_avancado.py`, que consulta `https://arquivo.pt/wayback/cdx` com `url=domain`, `from=20110101`, `to=20211231`, `output=json` e `fl=timestamp`, e conta as linhas de timestamp devolvidas. O valor no modelo (`relatorio_produto_cassandra.csv`) reflete este valor ou, quando o valor bruto de fase 2 é zero, a imputação mediana usada pelo pipeline.

---

## 4. `capture_density`

Fórmula do modelo:

`capture_density = Total_Arquivo_Captures / Pop. 2021`

No Evidence Pack, `capture_density` é calculada com `model_total_arquivo_captures` e a coluna demográfica `Pop. 2021`, seguindo `modelo_preditivo_real.py` e `scripts/generate_charts.py`.

---

## 5. `digital_decay_rate`

“digital_decay_rate is imported as a legacy model feature from metricas_iei_completo.csv:Media_Dias_Entre_Capturas. The original derivation formula is not fully recoverable from the current repository.”

Por isso, este campo é auditável ao nível de coluna-fonte, mas não deve ser descrito como fórmula plenamente recuperada.

---

## 6. Porque os contadores do checkpoint diferem de `Total_Arquivo_Captures`

Exemplo: Alcácer do Sal

- `checkpoint_cdx_record_count`: 5000
- `checkpoint_valid_capture_count`: 4567
- `model_total_arquivo_captures`: 129

A diferença é esperada:

- o checkpoint CDX usa `domain/*`, não a mesma janela temporal, e está limitado a 5000 registos;
- a extração de fase 2/modelo usa `from=20110101`, `to=20211231`, `url=domain`, e conta linhas de timestamp devolvidas;
- portanto, os contadores do checkpoint são evidência de proveniência, não a mesma métrica de `Total_Arquivo_Captures`.

---

## 7. Ligações de replay

O campo `generated_arquivo_replay_url` é gerado sintaticamente como:

`https://arquivo.pt/wayback/{timestamp}/{url}`

Estas ligações não são verificadas por este script. O campo `replay_url_verified` fica `false` em todas as linhas geradas.

---

## 8. Estado da ablação

As métricas atuais do modelo completo são:

- **Acurácia global:** 66.1%
- **F1-macro:** 67.2%

Estas métricas vêm de `reports/model_metrics.json`. O ficheiro `arquivo_ablation_results.json` não está presente na árvore de trabalho atual, portanto este Evidence Pack não reclama conter evidência completa de ablação.

**Nota conservadora:** A ligação à ablação deve ser feita quando o artefacto `arquivo_ablation_results.json` for restaurado e validado.

---

## 9. Limitações restantes

- O checkpoint CDX é limitado localmente e não representa totais históricos completos.
- `digital_decay_rate` tem proveniência de coluna, mas a fórmula original não está totalmente recuperável no repositório atual.
- As ligações `generated_arquivo_replay_url` são geradas, não verificadas.
- Valores SHAP, probabilidades individuais, métricas de ablação e fórmulas ausentes no repositório não foram inventados.
- `cdx_checkpoint.json` não está incluído nem ligado como download público.

---

## Ficheiros gerados

| Ficheiro | Descrição |
|---|---|
| `data/arquivo_evidence_summary.csv` | Resumo por município/domínio |
| `data/arquivo_capture_samples.csv` | Amostras de capturas CDX por município |
| `data/arquivo_feature_audit.csv` | Auditoria de variáveis de modelo |
| `data/arquivo_evidence_pack.json` | Pacote JSON compacto para auditoria |
| `docs/ARQUIVO_EVIDENCE_PACK.md` | Este documento |
