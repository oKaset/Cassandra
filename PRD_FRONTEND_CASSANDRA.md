# PRD — Website CASSANDRA Oracle Engine

## 1) Visão do Produto

Criar um website premium, memorável e visualmente distinto, que transforme o trabalho do **CASSANDRA Oracle Engine** numa experiência digital digna de prémio de design, sem perder rigor analítico.

O website deve comunicar, de forma clara e emocional, o risco demográfico-digital dos 308 municípios de Portugal, usando storytelling visual, interação sofisticada e dados verificáveis.

---

## 2) Contexto do Projeto (Base Real)

Este PRD é baseado nos teus artefactos reais no repositório:

- `relatorio_produto_cassandra.csv` (dataset final com 308 municípios)
- `municipios.geojson` (geometria para mapa municipal)
- `app_cassandra.py` (produto atual em Streamlit)
- `modelo_preditivo_real.py` (pipeline preditivo + `CASSANDRA_Risk_Score`)
- assets analíticos:
  - `plot_correlacao.png`
  - `plot_validacao.png`
  - `shap_summary_cassandra.png`
  - `ablacao_validacao.png`

### 2.1) Dados finais disponíveis

Dataset final: **308 linhas** e colunas:

- `Município`
- `Var_Pop`
- `IEI_Score`
- `Total_Arquivo_Captures`
- `Live_StatusCode`
- `CASSANDRA_Risk_Tier`
- `CASSANDRA_Risk_Score`

Distribuição atual dos tiers:

- TIER 4 - Profecia CASSANDRA: **164**
- TIER 3 - Risco de Fuga: **78**
- TIER 2 - Estagnação: **28**
- TIER 1 - Resiliência: **38**

Distribuição atual de estado de portal:

- `200`: **240**
- `Dead`: **51**
- `Timeout`: **6**
- `503`: **5**
- `403`: **3**
- `404`: **2**
- `400`: **1**

---

## 3) Objetivo de Produto

Entregar uma nova experiência frontend que:

1. Eleve a perceção de valor do teu trabalho (impacto visual e reputacional).
2. Permita exploração profunda por município sem fricção.
3. Torne o modelo compreensível para público técnico e não técnico.
4. Seja forte o suficiente para portfólio, jurados de design, media e stakeholders públicos.

### 3.1) Objetivos de sucesso

- O utilizador entende o que é CASSANDRA em menos de 15 segundos.
- O utilizador consegue encontrar qualquer município em menos de 10 segundos.
- O utilizador percebe visualmente diferenças de risco sem ler documentação técnica.
- A experiência transmite “produto premium”, não “dashboard genérico”.

---

## 4) Público-Alvo

- Decisores públicos e equipas municipais.
- Jornalistas, analistas e investigadores.
- Cidadãos interessados em desenvolvimento territorial.
- Parceiros institucionais e potenciais financiadores.

---

## 5) Proposta de Valor

"Uma plataforma de inteligência territorial que une sinais demográficos e saúde digital para antecipar risco municipal, com leitura visual instantânea e profundidade analítica."

---

## 6) Escopo Funcional (MVP de Alto Impacto)

## 6.1) Secção Hero Cinemática

- Headline forte + subheadline curta.
- KPIs principais visíveis sem scroll:
  - total municípios
  - número por tier
  - percentagem crítica (Tier 4)
- CTA: “Explorar Mapa” e “Ver Metodologia”.

## 6.2) Mapa Interativo de Risco (Core)

- Choropleth por município com `CASSANDRA_Risk_Tier`.
- Hover rico com:
  - Município
  - Tier
  - `Var_Pop`
  - `IEI_Score`
  - `Live_StatusCode`
  - `CASSANDRA_Risk_Score`
- Filtros por tier e estado do portal.
- Legenda semântica fixa.

## 6.3) Exploração Municipal

- Pesquisa por município (ignorar acentos).
- Painel de detalhe com:
  - risco (%), tier, saúde digital, variação populacional, capturas
- Estado visual do risco com codificação cromática.

## 6.4) Radar Regional

- Comparação do município selecionado com o melhor do distrito.
- Mostrar gap percentual de risco e mensagem contextual.

## 6.5) Simulador de Intervenção (PRR)

- Slider de simulação de `IEI_Score`.
- Projeção visual de redução de risco.
- Nota clara de que é simulação heurística.

## 6.6) Oracle Log (Tabela)

- Tabela filtrável/sortable com todos os municípios.
- Destaque visual por tier.
- Opção de download CSV.

## 6.7) Secção “Como funciona” (Metodologia)

- Explicação curta do pipeline:
  - dados IEI
  - dados demográficos
  - dados de atividade digital
  - classificação final
- Bloco de credibilidade com os plots existentes:
  - correlação
  - validação
  - SHAP
  - ablação

---

## 7) Requisitos de Design (Award-Worthy)

## 7.1) Direção Criativa

Criar uma linguagem visual entre:

- **editorial de investigação** (credibilidade)
- **experiência imersiva premium** (impacto emocional)
- **produto cívico futurista** (inovação)

Evitar aparência de template/dashboard padrão.

## 7.2) Sistema Visual

- Paleta base da marca CASSANDRA:
  - risco crítico: `#FF3366`
  - alerta: `#FFAA00`
  - moderado: `#FFD166`
  - resiliente: `#00E5FF`
  - neutro: `#8A93A6`
- Background atmosférico (gradientes + ruído subtil + profundidade).
- Cartões com materialidade premium (vidro/metal suave, sombras controladas).

## 7.3) Tipografia

- Evitar stacks genéricas (`Inter`, `Arial`, `Roboto` como default).
- Combinação recomendada:
  - Display: `Space Grotesk` ou `Sora`
  - Texto corrido: `Manrope` ou `Plus Jakarta Sans`
- Escala tipográfica expressiva, com hierarquia forte no hero e nos números.

## 7.4) Motion

- Transições com intenção (400–700ms, easing elegante).
- Staggered reveals por secção.
- Microinterações em hover/focus.
- Transições entre estados de filtro sem “flash” brusco.

## 7.5) Narrativa Visual

Sequência da página:

1. Choque visual (hero + estatística crítica)
2. Compreensão espacial (mapa)
3. Compreensão local (detalhe municipal)
4. Evidência técnica (metodologia + validação)
5. Chamada à ação (contacto/demo/download)

---

## 8) Requisitos Técnicos para Frontend

## 8.1) Stack sugerida

- `Next.js` + `TypeScript`
- styling: `Tailwind` ou CSS Modules com design tokens
- mapas: `Mapbox GL` ou `MapLibre`
- gráficos: `ECharts` ou `D3`/`Plotly`
- motion: `Framer Motion`

## 8.2) Contratos de dados

Frontend deve consumir:

- `relatorio_produto_cassandra.csv` (ou versão JSON normalizada)
- `municipios.geojson`

Normalização obrigatória:

- chaves consistentes por município (slug normalizado sem acentos)
- coerção de tipos numéricos
- fallback seguro para missing values (`N/D`)

## 8.3) Performance

- LCP alvo: < 2.5s em desktop moderno.
- Lazy loading de secções abaixo da dobra.
- Otimização de GeoJSON (simplificação/topojson se necessário).
- Transições suaves sem sacrificar FPS.

## 8.4) Acessibilidade

- WCAG 2.2 AA.
- Navegação por teclado em filtros, pesquisa e mapa.
- Contraste mínimo em todos os tiers.
- Tooltips e gráficos com alternativas textuais.

## 8.5) Responsividade

- Mobile-first funcional (sem degradar exploração).
- Breakpoints para desktop editorial e ecrãs grandes.
- Componentes críticos (mapa e detalhe municipal) com UX dedicada para mobile.

---

## 9) Requisitos de Conteúdo

## 9.1) Mensagens-chave

- "Risco demográfico-digital é mensurável."
- "O território pode ser comparado, priorizado e intervencionado."
- "CASSANDRA transforma sinais dispersos numa leitura acionável."

## 9.2) Tom de voz

- Sério, confiante, estratégico.
- Sem sensacionalismo gratuito.
- Clareza pública com profundidade técnica opcional.

---

## 10) Analytics e Medição

Eventos mínimos:

- filtro alterado (tier/status)
- município pesquisado
- município selecionado
- uso do simulador
- download de dados
- scroll depth por secção

KPIs de produto:

- tempo médio de sessão
- taxa de interação com mapa
- taxa de exploração municipal
- taxa de conclusão até secção metodologia

---

## 11) Critérios de Aceitação

1. O frontend renderiza os 308 municípios corretamente no mapa e tabela.
2. Filtros por tier/status afetam mapa, KPIs e tabela de forma consistente.
3. Pesquisa encontra municípios com e sem acentos.
4. Detalhe municipal mostra todos os campos principais sem quebra.
5. Simulador atualiza projeção de risco em tempo real.
6. Layout mantém qualidade premium em desktop e mobile.
7. Performance e acessibilidade cumprem requisitos mínimos.

---

## 12) Fora de Escopo (nesta fase)

- Re-treino do modelo em runtime no frontend.
- Backend complexo com autenticação multi-tenant.
- CMS completo para edição de narrativa.
- Edição colaborativa em tempo real.

---

## 13) Riscos e Mitigações

- Risco: mapa pesado em dispositivos fracos.
  - Mitigação: simplificar geometrias e carregar progressivamente.

- Risco: sobrecarga visual prejudicar clareza.
  - Mitigação: design system com prioridades de leitura e testes de usabilidade.

- Risco: interpretação política sensível dos tiers.
  - Mitigação: contexto metodológico claro e disclaimers explícitos.

---

## 14) Entregáveis Esperados do Frontend Engineer

1. Website funcional em ambiente de produção.
2. Design system (tokens, componentes, estados).
3. Código documentado de ingestão/normalização de dados.
4. Implementação completa de mapa, filtros, detalhe municipal e simulador.
5. Secção de metodologia com assets analíticos.
6. Checklist de performance + acessibilidade + QA responsivo.

---

## 15) Prompt de handoff (copiar e enviar ao frontend engineer)

"Quero que construas uma experiência web premium e diferenciada para o projeto CASSANDRA Oracle Engine, usando os datasets `relatorio_produto_cassandra.csv` e `municipios.geojson`. O objetivo é criar um produto com qualidade de prémio de design: impacto visual alto, storytelling claro e interação fluida. Prioriza mapa interativo por tier, exploração municipal, simulador de intervenção e secção de metodologia com credibilidade analítica. Não quero visual de dashboard genérico; quero direção editorial imersiva, motion elegante, tipografia forte e execução impecável em desktop e mobile." 
