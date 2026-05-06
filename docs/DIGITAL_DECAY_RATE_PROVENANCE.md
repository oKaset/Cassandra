# Proveniência de `digital_decay_rate`

## Enquadramento

`digital_decay_rate` é mantida como variável Arquivo.pt com proveniência de coluna documentada, mas não como variável com fórmula original totalmente recuperável. Por isso, o argumento central da candidatura não deve depender exclusivamente dela.

Esta nota documenta o que é recuperável no repositório actual e onde permanece a limitação metodológica.

## Coluna-fonte e ficheiro-fonte

- **Coluna-fonte:** `Media_Dias_Entre_Capturas`
- **Ficheiro-fonte:** `metricas_iei_completo.csv`
- **Colunas disponíveis no ficheiro-fonte:** `Domain`, `Município`, `Media_Dias_Entre_Capturas`, `IEI_Score`

A coluna existe como valor numérico por município/domínio. A sua proveniência de coluna é, portanto, auditável no ficheiro que alimenta o pipeline.

## Onde entra no modelo

Em `modelo_preditivo_real.py`, o pipeline localiza a coluna `Media_Dias_Entre_Capturas` ou `Média_Dias_Entre_Capturas` e mapeia-a para:

```python
df["digital_decay_rate"] = df[col_decay]
```

Depois, `digital_decay_rate` entra no conjunto de variáveis candidatas do modelo juntamente com `IEI_Score`, `Total_Arquivo_Captures`, `capture_density`, `is_coastal`, `Pop. 2011`, `Env. 2001` e `Var% 2001→2011`.

Em `scripts/generate_charts.py`, a mesma relação é preservada no `load_training_data()`: a coluna `Media_Dias_Entre_Capturas` é lida e emitida como `digital_decay_rate` no dataframe de treino.

Em `scripts/build_arquivo_evidence_pack.py`, a origem é documentada como `metricas_iei_completo.csv:Media_Dias_Entre_Capturas` e a variável é marcada como variável legada com limitação de fórmula.

## O que é recuperável

- O ficheiro e a coluna que fornecem `digital_decay_rate`.
- A passagem directa de `Media_Dias_Entre_Capturas` para `digital_decay_rate` no pipeline de treino.
- A presença da variável no conjunto de features usado pela ablação pública validada.
- A distinção entre esta variável temporal legada e as variáveis Arquivo Core totalmente auditáveis: `Total_Arquivo_Captures` e `capture_density`.
- A estrutura do checkpoint CDX local não publicado: um objecto por domínio, com listas de registos CDX que incluem campos como `timestamp`, `url`, `status`, `mime`, `digest`, `filename`, `collection` e `source`.

## O que não é recuperável

- A fórmula original completa que gerou `Media_Dias_Entre_Capturas`.
- O script ou commit original que derivou essa coluna a partir dos registos Arquivo.pt.
- Uma recomputação completa de `digital_decay_rate` apenas com os artefactos actuais.
- Garantia de que o checkpoint CDX local não publicado contém a mesma janela, filtros, deduplicação e agregação usados para produzir `Media_Dias_Entre_Capturas`.

O checkpoint CDX local permite auditar evidência temporal e construir estatísticas alternativas, mas está limitado localmente e não deve ser tratado como fonte suficiente para reconstruir a fórmula original de `Media_Dias_Entre_Capturas`.

## Porque isto não invalida o argumento Arquivo.pt

A limitação afecta uma variável temporal legada, não toda a cadeia de evidência Arquivo.pt. O projecto já distingue:

- valores brutos ou de checkpoint;
- valores de entrada do modelo;
- imputação;
- qualidade da evidência;
- métricas públicas confirmadas por ablação.

Além disso, `Total_Arquivo_Captures` e `capture_density` têm fórmula e proveniência auditáveis no repositório actual. A ablação pública validada continua a demonstrar uma contribuição funcional mensurável do conjunto de variáveis Arquivo.pt, sem transformar essa evidência numa alegação determinística.

## Como o Arquivo Core Robustness Check reduz o risco

O `Arquivo Core Robustness Check` acrescenta uma verificação secundária que separa:

- **variáveis Arquivo Core totalmente auditáveis:** `Total_Arquivo_Captures` e `capture_density`;
- **variável temporal legada:** `digital_decay_rate`.

Esta verificação não substitui as métricas públicas confirmadas. O seu papel é tornar explícito se a contribuição Arquivo.pt permanece observável quando o núcleo auditável é isolado, e impedir que a candidatura dependa exclusivamente de uma variável cuja fórmula original não está totalmente recuperável.
