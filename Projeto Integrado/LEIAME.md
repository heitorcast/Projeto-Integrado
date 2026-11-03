# 🚌 Transporte e Mobilidade Urbana — Números que Falam

Projeto Integrador Python + Matemática · Indicador 5 · Censo 2022 (IBGE/SIDRA)

## 1. Como rodar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Sem arquivo enviado, o app abre com **dados fictícios de demonstração** (aviso amarelo no topo).
Eles servem só para ver o painel funcionando. **Antes de apresentar, envie a base real do IBGE.**

## 2. Como trazer os dados reais (SIDRA)

1. Acesse sidra.ibge.gov.br → **Censo Demográfico 2022** → tema de **trabalho / deslocamento**
   (divulgação "Deslocamentos para trabalho e para estudo", outubro/2025).
2. Procure a tabela com **meio de transporte** (e, se possível, **cor ou raça** e **tempo habitual de
   deslocamento**). Nível territorial: **Município** (melhor para o ranking de bicicleta) ou **UF**.
3. Baixe em **CSV ou XLSX**.
4. No app: envie o arquivo na barra lateral. Se o arquivo tiver linhas de título antes do cabeçalho,
   ajuste "Linhas a ignorar". Confira o **Mapeamento de colunas** (o app sugere automaticamente).
5. Se o arquivo trouxer mais de uma variável (ex.: "Pessoas" e "Percentual"), use o
   **Filtro de linhas** para manter só a contagem de pessoas.

O app remove linhas "Total" para não contar duas vezes. Se faltar uma coluna (renda, raça, tempo),
as abas que dependem dela avisam em vez de quebrar. Pode enviar tabelas diferentes uma de cada vez
(ex.: uma para meio × raça, outra para tempo × meio).

## 3. Mapa da rubrica → onde está no app

| Critério | O que o app faz |
|---|---|
| 1. ETL, upload e filtros (0,75) | `st.file_uploader` CSV/XLSX; limpeza automática; filtros de região, UF, raça, renda e meio |
| 2. Rigor estatístico e perguntas (0,90) | Aba **Estatística descritiva** (média, mediana, moda, Q1, Q3, IQR, amplitude, variância, desvio, outliers 1,5·IQR + texto de interpretação) e aba **Respostas às perguntas** |
| 3. Visualização e conteúdo extra (0,60) | Barras agrupadas, boxplots, roscas, ranking, histograma; aba **Notícias e imagens** |
| 4. Apresentação (0,75) | Roteiro abaixo |

## 4. As 3 perguntas da persona

1. **Mediana por meio de transporte e raça (KPI):** aba 1. Escolha "Tempo de deslocamento (min)" ou
   "Nº de pessoas por município/UF". O enunciado não diz mediana *de quê*; confirme com a Profa. Conceição.
2. **% público × particular × ativo:** aba 2 (KPIs no topo + roscas).
3. **Cidades com mais bicicleta:** aba 4 (ranking).

## 5. Matemática que você precisa saber explicar

- **Mediana de dados agrupados:** o IBGE publica o tempo em faixas (ex.: "até 5 min", "6 min a meia hora").
  A mediana é calculada por interpolação dentro da faixa que contém o ponto central:
  `Q = L + ((p·N − F_ant) / f) · h` (L = limite inferior da classe, F_ant = frequência acumulada anterior,
  f = frequência da classe, h = amplitude). Para p = 0,5 é a mediana; p = 0,25 e 0,75 dão Q1 e Q3.
- **IQR = Q3 − Q1**; **outlier** = valor fora de `[Q1 − 1,5·IQR ; Q3 + 1,5·IQR]`.
- **Média × mediana:** outliers puxam a média, não a mediana. Em tempo de deslocamento, a mediana
  descreve melhor o trabalhador "típico".
- **Variância/desvio padrão** (amostrais, n−1): dispersão em torno da média; o coeficiente de variação
  (desvio ÷ média) permite comparar variáveis de escalas diferentes.
- **Premissa:** a faixa aberta "mais de 2 horas" foi limitada a 180 min (editável na barra lateral).

## 6. Roteiro de apresentação (sem ler a tela)

Você é analista de uma startup de dados atendendo Fernando, Ana, Luciene, Pedrinho e Lucas.

1. **Abertura (30 s):** "Vimos como o brasileiro vai ao trabalho e quanto tempo gasta, por raça e renda."
2. **Pergunta 2 (45 s):** os três percentuais (público, particular, ativo) e o que significam para a Luciene
   (Vitória) e o Pedrinho (BH).
3. **Pergunta 1 (60 s):** a mediana por modal e raça; quem leva mais tempo e por quê isso é desigualdade.
4. **Outliers (45 s):** boxplot; gargalos; por que a mediana é melhor que a média aqui.
5. **Pergunta 3 (30 s):** ranking de bicicleta; recomendação de ciclovias para a Ana e o Lucas.
6. **Fechamento (30 s):** uma decisão concreta por persona.

Treine responder: "por que mediana e não média?", "o que é IQR?", "como você tratou o tempo em faixas?",
"o que é um outlier aqui?", "de onde vêm os dados?".

## 7. Arquivos

- `app.py` — interface Streamlit.
- `nucleo.py` — leitura/limpeza, mediana e quartis de dados agrupados, estatística descritiva, dados de demonstração.
- `requirements.txt` — dependências.
- `imagens/` — coloque 3 a 6 fotos livres (cite a fonte).

## 8. Integração com o grupo

Para juntar os 5 indicadores num painel único, o grupo cria um `Home.py` com uma pasta `pages/`.
Copie este `app.py` para `pages/5_Mobilidade_Urbana.py`, copie `nucleo.py` para a **raiz** (junto do `Home.py`),
mantenha a pasta `imagens/` na raiz e rode `streamlit run Home.py` na raiz. O Streamlit mostra a navegação
entre as páginas na barra lateral. Combinem antes: mesmos nomes de colunas nos filtros e um `requirements.txt` único.
