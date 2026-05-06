# Pacote de Evidências Arquivo.pt — CASSANDRA
## Documento para Auditoria por Júri

**Gerado em:** 2026-05-06T01:33:23.049770+00:00
**Fontes de métricas públicas confirmadas:** `reports/confirmed_model_metrics.json`, `data/arquivo_ablation_summary.json`, `arquivo_ablation_results.json`

---

## 1. O que contém o checkpoint CDX local?

O registo CDX local (não publicado) contém entradas extraídas da API pública do Arquivo.pt para os domínios municipais portugueses. Cada entrada inclui: URL, timestamp, MIME type, HTTP status, digest, filename, collection e source.

Este checkpoint não é copiado para a documentação nem publicado como anexo. O checkpoint tem 1,521,598 registos para 308 domínios; 301/308 domínios estão exatamente no limite local de 5000 registos definido por `cassandra_opcao_a.py`.

**Definição crítica:** `checkpoint_cdx_record_count` reflecte os registos disponíveis no checkpoint local limitado; não é um total histórico completo de todas as capturas Arquivo.pt.

**Definição de validade:** `checkpoint_valid_capture_count` conta registos do checkpoint com status 200, 301, 302 ou 304.

---

## 2. Diferença entre checkpoint e variáveis do modelo

| Conceito | Fonte | Significado |
|---|---|---|
| `checkpoint_cdx_record_count` | checkpoint CDX local não publicado | Número de registos disponíveis no checkpoint local limitado; não é total histórico completo |
| `checkpoint_valid_capture_count` | checkpoint CDX local não publicado | Registos do checkpoint com status 200, 301, 302 ou 304 |
| `model_total_arquivo_captures` | `relatorio_produto_cassandra.csv` | Valor de `Total_Arquivo_Captures` usado pelo modelo |
| `capture_count_imputed` | derivado | `yes` quando o modelo usou o valor mediano (628) em vez do valor bruto da fase 2 |

Os campos do checkpoint são evidência de proveniência local. Não são apresentados como valores de entrada do modelo.

---

## 3. Como é calculado `Total_Arquivo_Captures`?

O valor é calculado por `extrator_fase2_avancado.py`. Este script consulta `https://arquivo.pt/wayback/cdx` com os parâmetros `url=domain`, `from=20110101`, `to=20211231`, `output=json` e `fl=timestamp`, e conta as linhas de timestamp devolvidas. O valor que entra no modelo (`relatorio_produto_cassandra.csv`) é este resultado ou, quando é zero, a mediana usada pelo pipeline como substituição.

---

## 4. `capture_density`

Fórmula do modelo:

`capture_density = Total_Arquivo_Captures / Pop. 2021`

No Evidence Pack, `capture_density` é calculada com `model_total_arquivo_captures` e a coluna demográfica `Pop. 2021`, seguindo `modelo_preditivo_real.py` e `scripts/generate_charts.py`.

---

## 5. `digital_decay_rate`

`digital_decay_rate` é importada como variável histórica a partir de `metricas_iei_completo.csv:Media_Dias_Entre_Capturas`. A fórmula que a gerou não está totalmente recuperável no repositório actual.

Este campo pode ser rastreado até à coluna de origem, mas não deve ser apresentado como fórmula totalmente recuperada.

---

## Robustez metodológica: variáveis Arquivo Core

As variáveis do Arquivo.pt com auditoria completa são `Total_Arquivo_Captures` e `capture_density`. A primeira é o valor de entrada do modelo, distinto dos contadores de checkpoint. A segunda é calculada por fórmula directa:

`capture_density = Total_Arquivo_Captures / Pop. 2021`

`digital_decay_rate` tem origem documentada ao nível da coluna, mas a fórmula original não é recuperável. Por isso, o argumento principal não deve assentar exclusivamente nesta variável.

O projecto inclui o `Arquivo Core Robustness Check` (resumo em `data/arquivo_core_robustness_summary.json`) para medir a contribuição das variáveis Arquivo.pt sem sobrestimar a variável herdada. Na execução actual, o teste funciona como verificação secundária e é conservador: retirar todas as variáveis Arquivo.pt altera a exactidão em -0,3490 pp e o F1 ponderado em -0,3954 pp; retirar apenas as variáveis Arquivo Core, mantendo `digital_decay_rate`, altera a exactidão em +1,2586 pp e o F1 ponderado em +1,2130 pp.

Este resultado não substitui a ablação pública validada. Serve para explicitar a limitação de proveniência de `digital_decay_rate` e garantir que o argumento não depende exclusivamente desta variável.

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

O campo `generated_arquivo_replay_url` é construído automaticamente com o formato:

`https://arquivo.pt/wayback/{timestamp}/{url}`

Estas ligações não são verificadas por este script. O campo `replay_url_verified` fica `false` em todas as linhas geradas.

---

## 8. Estado da ablação

As métricas públicas confirmadas são:

- **Com Arquivo.pt:** exatidão global 66,13%; F1 ponderado 64,90%
- **Sem Arquivo.pt:** exatidão global 58,06%; F1 ponderado 58,19%

Estas métricas vêm do artefacto restaurado `arquivo_ablation_results.json` e foram cruzadas com `reports/confirmed_model_metrics.json`. O resumo validado está em `data/arquivo_ablation_summary.json`.

## Ligação à ablação

O Evidence Pack associa as variáveis derivadas do Arquivo.pt (`Total_Arquivo_Captures`, `capture_density`, `digital_decay_rate`) ao resumo validado de ablação. A remoção destas variáveis reduz a exactidão global em 8,06 pontos percentuais e o F1 ponderado em 6,71 pontos percentuais — evidência de que a memória digital arquivada contém sinal territorial mensurável.

---

## 9. Limitações restantes

- O checkpoint CDX é limitado localmente e não representa totais históricos completos.
- `digital_decay_rate` tem proveniência de coluna, mas a fórmula original não está totalmente recuperável no repositório atual.
- O `Arquivo Core Robustness Check` é uma verificação secundária e não deve ser usado para reforçar a alegação principal sobre as variáveis Arquivo Core.
- As ligações `generated_arquivo_replay_url` são geradas, não verificadas.
- Valores SHAP, probabilidades individuais e fórmulas ausentes no repositório não foram inventados; as métricas de ablação vêm apenas do artefacto restaurado e validado.
- O checkpoint CDX local não está incluído nem ligado como download público.

---

## Ficheiros gerados

| Ficheiro | Descrição |
|---|---|
| `data/arquivo_evidence_summary.csv` | Resumo por município/domínio |
| `data/arquivo_capture_samples.csv` | Amostras de capturas CDX por município |
| `data/arquivo_feature_audit.csv` | Auditoria de variáveis de modelo |
| `data/arquivo_evidence_pack.json` | Pacote JSON compacto para auditoria |
| `data/arquivo_core_robustness_summary.json` | Verificação secundária de robustez das variáveis Arquivo Core |
| `docs/DIGITAL_DECAY_RATE_PROVENANCE.md` | Nota de proveniência e limitação de `digital_decay_rate` |
| `docs/ARQUIVO_EVIDENCE_PACK.md` | Este documento |
