"""
Números que Falam — Descobrindo o Brasil
Indicador 5: Transporte e Mobilidade Urbana (IBGE — Censo 2022: deslocamentos para o trabalho)

Executar:  streamlit run app.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import nucleo as nc

st.set_page_config(page_title="Mobilidade Urbana — Números que Falam", page_icon="🚌", layout="wide")

PASTA_IMAGENS = next((p for p in (Path(__file__).parent / "imagens", Path.cwd() / "imagens") if p.exists()),
                     Path(__file__).parent / "imagens")


# --------------------------------------------------------------------------
# Auxiliares de interface (compatíveis com várias versões do Streamlit)
# --------------------------------------------------------------------------
def mostrar_grafico(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except Exception:
        st.plotly_chart(fig, use_container_width=True)


def mostrar_tabela(df, **kw):
    try:
        st.dataframe(df, width="stretch", **kw)
    except Exception:
        st.dataframe(df, use_container_width=True, **kw)


@st.cache_data(show_spinner=False)
def carregar_demo():
    return nc.generate_demo()


@st.cache_data(show_spinner=False)
def carregar_arquivo(dados: bytes, nome: str, pular: int):
    return nc.read_uploaded(dados, nome, pular)


# --------------------------------------------------------------------------
# Barra lateral: upload, mapeamento e filtros
# --------------------------------------------------------------------------
st.sidebar.title("🚌 Mobilidade Urbana")
st.sidebar.caption("Indicador 5 · Censo 2022 (IBGE/SIDRA)")

arquivo = st.sidebar.file_uploader("📂 Envie a base do IBGE (CSV ou XLSX)", type=["csv", "xlsx", "xls"])
pular = st.sidebar.number_input("Linhas a ignorar no topo do arquivo", min_value=0, max_value=50, value=0,
                                help="Exportações do SIDRA costumam ter linhas de título antes do cabeçalho.")
usa_demo = arquivo is None

if usa_demo:
    bruto = carregar_demo()
    mapa = {c: c for c in bruto.columns}
    st.sidebar.warning("Sem arquivo enviado: usando **dados FICTÍCIOS de demonstração** (não são do IBGE).")
else:
    try:
        bruto = carregar_arquivo(arquivo.getvalue(), arquivo.name, int(pular))
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        st.stop()
    sugestao = nc.adivinhar_mapeamento(list(bruto.columns))
    with st.sidebar.expander("🧭 Mapeamento de colunas", expanded=True):
        st.caption("Diga qual coluna do arquivo corresponde a cada campo.")
        opcoes = ["(não possui)"] + list(bruto.columns)
        mapa = {}
        for canon, rotulo in nc.CANONICAS.items():
            padrao = sugestao.get(canon)
            escolha = st.selectbox(rotulo, opcoes, index=opcoes.index(padrao) if padrao in opcoes else 0,
                                   key=f"map_{canon}")
            mapa[canon] = None if escolha == "(não possui)" else escolha
    with st.sidebar.expander("🔎 Filtro de linhas do arquivo (opcional)"):
        st.caption("Use se o arquivo tiver várias variáveis (ex.: 'Pessoas' e 'Percentual') para não somar tudo junto.")
        col_f = st.selectbox("Coluna", ["(nenhuma)"] + list(bruto.columns), key="linha_col")
        if col_f != "(nenhuma)":
            vals = sorted(bruto[col_f].dropna().astype(str).unique())
            manter = st.multiselect("Manter apenas", vals, default=vals[:1], key="linha_vals")
            bruto = bruto[bruto[col_f].astype(str).isin(manter)]

try:
    base = nc.prepare(bruto, mapa)
except Exception as e:
    st.error(f"Não foi possível tratar os dados: {e}")
    st.stop()
if base.empty:
    st.error("Depois da limpeza não sobraram linhas. Confira o mapeamento de colunas e as linhas ignoradas.")
    st.stop()

tem = lambda c: c in base.columns  # noqa: E731
TEM_TEMPO = tem("faixa_tempo")
TEM_MEIO = tem("meio")
TEM_RACA = tem("cor_raca")

if not TEM_MEIO:
    st.error("Mapeie a coluna **Meio de transporte** na barra lateral para continuar.")
    st.stop()

# Faixas de tempo editáveis (premissa de cálculo para dados agrupados)
if TEM_TEMPO:
    with st.sidebar.expander("⏱️ Limites das faixas de tempo (min)"):
        st.caption("O Censo agrupa o tempo em faixas. Estes limites alimentam mediana e quartis.")
        faixas = st.data_editor(nc.faixa_table(base), hide_index=True, disabled=["faixa"], key="faixas")
    base = nc.apply_faixas(base, faixas)

# Grupos de modais editáveis
with st.sidebar.expander("🚦 Classificação dos modais"):
    st.caption("Público × Particular × Ativo (editável).")
    tab_grupos = pd.DataFrame({"meio": sorted(base["meio"].unique())})
    tab_grupos["grupo"] = tab_grupos["meio"].map(nc.classificar_meio)
    tab_grupos = st.data_editor(
        tab_grupos, hide_index=True, disabled=["meio"], key="grupos",
        column_config={"grupo": st.column_config.SelectboxColumn("grupo", options=nc.GRUPOS, required=True)})
base["grupo"] = base["meio"].map(dict(zip(tab_grupos["meio"], tab_grupos["grupo"])))

st.sidebar.markdown("---")
st.sidebar.subheader("Filtros")


def filtro(rotulo, coluna, dados, opcoes=None):
    if coluna not in dados.columns:
        return None
    opcoes = opcoes if opcoes is not None else sorted(dados[coluna].dropna().unique())
    return st.sidebar.multiselect(rotulo, opcoes, default=list(opcoes), key=f"f_{coluna}")


sel_regiao = filtro("Região", "regiao", base)
dados = base[base["regiao"].isin(sel_regiao)] if sel_regiao is not None else base
sel_uf = filtro("UF / Região Metropolitana", "uf", dados)
if sel_uf is not None:
    dados = dados[dados["uf"].isin(sel_uf)]
sel_raca = filtro("Cor ou raça", "cor_raca", dados)
if sel_raca is not None:
    dados = dados[dados["cor_raca"].isin(sel_raca)]
sel_renda = filtro("Categoria de renda", "renda", dados)
if sel_renda is not None:
    dados = dados[dados["renda"].isin(sel_renda)]
sel_meio = filtro("Meio de transporte", "meio", dados)

df_base = dados  # percentuais: denominador = todos os modais
df_f = dados[dados["meio"].isin(sel_meio)] if sel_meio else dados.iloc[0:0]
st.sidebar.caption("O filtro de meio de transporte não altera os percentuais de uso (o denominador "
                   "continua sendo todos os modais); ele afeta os gráficos de tempo e a rosca.")

if df_base.empty or df_f.empty:
    st.warning("Nenhum dado com os filtros escolhidos. Ajuste a barra lateral.")
    st.stop()

# --------------------------------------------------------------------------
# Cabeçalho + KPIs
# --------------------------------------------------------------------------
st.title("🚌 Transporte e Mobilidade Urbana")
st.caption("Números que Falam — Descobrindo o Brasil · Projeto Integrador Python + Matemática · "
           "Fonte: IBGE, Censo Demográfico 2022 (deslocamentos para o trabalho)")
if usa_demo:
    st.warning("⚠️ **Dados fictícios de demonstração.** Envie o arquivo do SIDRA na barra lateral para ver os "
               "resultados reais. Nenhum número desta tela, enquanto este aviso estiver visível, vem do IBGE.")

with st.expander("👥 Persona e cenário"):
    st.markdown(
        "**Equipe:** Fernando (Secretário Nacional de Mobilidade Urbana), Ana (Gestora de Transportes da RM de "
        "Goiânia), Luciene (Prefeita de Vitória), Pedrinho (Prefeito de Belo Horizonte) e Lucas (Especialista em "
        "Logística de Brasília).\n\n**Missão:** avaliar os modais de transporte mais utilizados, por raça, para "
        "orientar decisões de mobilidade. Somos uma startup de análise de dados.")

pct = df_base.groupby("grupo")["pessoas"].sum() / df_base["pessoas"].sum() * 100
por_meio = df_base.groupby("meio")["pessoas"].sum().sort_values(ascending=False)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Pessoas (filtro atual)", f"{df_base['pessoas'].sum():,.0f}".replace(",", "."))
k2.metric("Transporte público", f"{pct.get('Público', 0):.1f}%")
k3.metric("Particular (carro/moto)", f"{pct.get('Particular', 0):.1f}%")
k4.metric("Ativo (bicicleta/a pé)", f"{pct.get('Ativo', 0):.1f}%")
k5.metric("Modal predominante", por_meio.index[0], f"{por_meio.iloc[0] / por_meio.sum() * 100:.1f}%")
if TEM_TEMPO:
    geral = nc.tempo_stats_by(df_f, []).iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Mediana do tempo de deslocamento", f"{geral['Mediana']:.1f} min")
    c2.metric("Q1 – Q3", f"{geral['Q1']:.0f} – {geral['Q3']:.0f} min")
    c3.metric("IQR (dispersão da metade central)", f"{geral['IQR']:.1f} min")

abas = st.tabs(["1️⃣ Mediana por modal e raça", "2️⃣ Público × particular × ativo", "3️⃣ Tempo e outliers",
                "4️⃣ Mobilidade ativa (bicicleta)", "📐 Estatística descritiva", "📝 Respostas às perguntas",
                "📰 Notícias e imagens", "ℹ️ Fonte e método"])

# --------------------------------------------------------------------------
# Aba 1 — Mediana por modal e raça
# --------------------------------------------------------------------------
with abas[0]:
    st.subheader("Qual é a mediana por meio de transporte, por raça?")
    opcoes_metrica = []
    if TEM_TEMPO:
        opcoes_metrica.append("Tempo de deslocamento (min)")
    opcoes_metrica.append("Nº de pessoas por município/UF")
    metrica = st.radio("Mediana de quê?", opcoes_metrica, horizontal=True)
    eixo_raca = ["cor_raca"] if TEM_RACA else []
    if metrica.startswith("Tempo"):
        tab = nc.tempo_stats_by(df_f, ["meio"] + eixo_raca)
        valor, unid = "Mediana", "min"
        st.caption("Mediana de dados agrupados em faixas (interpolação linear dentro da faixa). "
                   "Limites das faixas editáveis na barra lateral.")
    else:
        g = df_f.groupby(["unidade", "meio"] + eixo_raca, as_index=False)["pessoas"].sum()
        tab = g.groupby(["meio"] + eixo_raca, as_index=False)["pessoas"].median().rename(columns={"pessoas": "Mediana"})
        valor, unid = "Mediana", "pessoas"
        st.caption("Mediana do nº de pessoas entre as unidades (município/UF) disponíveis.")
    colA, colB = st.columns([1, 2])
    with colA:
        m_sel = st.selectbox("Meio de transporte (KPI)", sorted(tab["meio"].unique()))
        if TEM_RACA:
            r_sel = st.selectbox("Cor ou raça (KPI)", sorted(tab["cor_raca"].unique()))
            lin = tab[(tab["meio"] == m_sel) & (tab["cor_raca"] == r_sel)]
        else:
            lin = tab[tab["meio"] == m_sel]
        if len(lin):
            st.metric(f"Mediana — {m_sel}", f"{lin[valor].iloc[0]:,.1f} {unid}".replace(",", "."))
        if TEM_RACA:
            piv = tab.pivot(index="meio", columns="cor_raca", values=valor).round(1)
            mostrar_tabela(piv)
    with colB:
        fig = px.bar(tab, x="meio", y=valor, color="cor_raca" if TEM_RACA else None, barmode="group",
                     labels={"meio": "Meio de transporte", valor: f"Mediana ({unid})", "cor_raca": "Cor ou raça"},
                     title=f"Mediana ({unid}) por meio de transporte" + (" e cor ou raça" if TEM_RACA else ""))
        mostrar_grafico(fig)

# --------------------------------------------------------------------------
# Aba 2 — Público x particular x ativo
# --------------------------------------------------------------------------
with abas[1]:
    st.subheader("Que parcela da população usa transporte público, particular ou ativo?")
    c1, c2 = st.columns(2)
    with c1:
        grp = df_base.groupby("grupo", as_index=False)["pessoas"].sum()
        fig = px.pie(grp, names="grupo", values="pessoas", hole=0.5, title="Grupos de modal (rosca)")
        fig.update_traces(textinfo="percent+label")
        mostrar_grafico(fig)
    with c2:
        m = df_f.groupby("meio", as_index=False)["pessoas"].sum()
        fig = px.pie(m, names="meio", values="pessoas", hole=0.5, title="Modal utilizado (rosca)")
        fig.update_traces(textinfo="percent")
        mostrar_grafico(fig)
    st.markdown("**Distribuição por grupo de modal**")
    por_grupo_raca = None
    if TEM_RACA:
        t = df_base.groupby(["cor_raca", "grupo"], as_index=False)["pessoas"].sum()
        fig = px.bar(t, x="cor_raca", y="pessoas", color="grupo", barnorm="percent",
                     labels={"cor_raca": "Cor ou raça", "pessoas": "% das pessoas", "grupo": "Grupo"},
                     title="Grupos de modal por cor ou raça (100%)")
        mostrar_grafico(fig)
    eixo = "uf" if tem("uf") else "unidade"
    t = df_base.groupby([eixo, "grupo"], as_index=False)["pessoas"].sum()
    fig = px.bar(t, x=eixo, y="pessoas", color="grupo", barnorm="percent",
                 labels={eixo: "UF" if eixo == "uf" else "Unidade", "pessoas": "% das pessoas", "grupo": "Grupo"},
                 title=f"Grupos de modal por {'UF' if eixo == 'uf' else 'unidade'} (100%)")
    mostrar_grafico(fig)

# --------------------------------------------------------------------------
# Aba 3 — Tempo e outliers
# --------------------------------------------------------------------------
with abas[2]:
    st.subheader("Tempo de deslocamento: gargalos e outliers")
    if not TEM_TEMPO:
        st.info("Mapeie a coluna de **faixa de tempo de deslocamento** para habilitar esta aba.")
    else:
        ts = nc.tempo_stats_by(df_f, ["meio"])
        fig = go.Figure()
        for _, r in ts.iterrows():
            inf = max(r["Q1"] - 1.5 * r["IQR"], r["Min"])
            sup = min(r["Q3"] + 1.5 * r["IQR"], r["Max"])
            fig.add_trace(go.Box(name=r["meio"], q1=[r["Q1"]], median=[r["Mediana"]], q3=[r["Q3"]],
                                 lowerfence=[inf], upperfence=[sup], boxpoints=False))
        fig.update_layout(title="Boxplot do tempo de deslocamento por modal (Q1, mediana, Q3 — dados agrupados)",
                          yaxis_title="Minutos", xaxis_title="Meio de transporte", showlegend=False)
        mostrar_grafico(fig)
        st.caption("As pontas das hastes seguem a regra 1,5·IQR, limitadas ao intervalo das faixas observadas.")

        st.markdown("**Dispersão entre municípios/UFs** — cada ponto é a mediana do tempo de uma unidade; "
                    "pontos isolados são outliers (gargalos).")
        tu = nc.tempo_stats_by(df_f, ["unidade", "meio"])
        fig = px.box(tu, x="meio", y="Mediana", points="outliers", hover_name="unidade",
                     labels={"meio": "Meio de transporte", "Mediana": "Mediana do tempo (min)"},
                     title="Mediana do tempo por unidade, segundo o modal")
        mostrar_grafico(fig)

        modal_gargalo = st.selectbox("Listar gargalos do modal", sorted(tu["meio"].unique()), key="gargalo")
        serie = tu[tu["meio"] == modal_gargalo].set_index("unidade")["Mediana"]
        est = nc.descriptive_stats(serie)
        if est:
            acima = serie[serie > est["Limite superior (Q3+1,5·IQR)"]].sort_values(ascending=False)
            if acima.empty:
                st.success(f"Nenhuma unidade é outlier superior no tempo de {modal_gargalo}.")
            else:
                st.warning(f"{len(acima)} unidade(s) com tempo mediano acima de "
                           f"{est['Limite superior (Q3+1,5·IQR)']:.1f} min em {modal_gargalo}:")
                mostrar_tabela(acima.rename("Mediana (min)").round(1).to_frame())

# --------------------------------------------------------------------------
# Aba 4 — Mobilidade ativa
# --------------------------------------------------------------------------
with abas[3]:
    st.subheader("Quais cidades têm mais mobilidade ativa?")
    meios_lista = sorted(df_base["meio"].unique())
    padrao = next((i for i, m in enumerate(meios_lista) if "bicicleta" in m.lower()), 0)
    c1, c2 = st.columns(2)
    modal_ativo = c1.selectbox("Modal", meios_lista, index=padrao, key="modal_ativo")
    topn = c2.slider("Quantas unidades no ranking", 5, 30, 10)
    pct_u = nc.unit_share(df_base, "meio", modal_ativo).sort_values(ascending=False)
    abs_u = df_base[df_base["meio"] == modal_ativo].groupby("unidade")["pessoas"].sum()
    rk = pd.DataFrame({"% de uso": pct_u.round(2), "Pessoas": abs_u.reindex(pct_u.index).fillna(0).astype(int)})
    fig = px.bar(rk.head(topn).iloc[::-1].reset_index(), x="% de uso", y="unidade", orientation="h",
                 labels={"unidade": "", "% de uso": f"% que usa: {modal_ativo}"},
                 title=f"Ranking — {modal_ativo} (% da população ocupada da unidade)")
    mostrar_grafico(fig)
    mostrar_tabela(rk.head(topn))

# --------------------------------------------------------------------------
# Aba 5 — Estatística descritiva
# --------------------------------------------------------------------------
with abas[4]:
    st.subheader("Estatística descritiva (entre municípios/UFs)")
    vars_ = ["% de uso de um modal", "Nº de pessoas por unidade"]
    if TEM_TEMPO:
        vars_.insert(1, "Mediana do tempo (min) por unidade")
    c1, c2 = st.columns(2)
    variavel = c1.radio("Variável", vars_, key="var_desc")
    meios_lista = sorted(df_base["meio"].unique())
    pad = next((i for i, m in enumerate(meios_lista) if "bicicleta" in m.lower()), 0)
    modal_d = c2.selectbox("Modal", meios_lista, index=pad, key="modal_desc")
    if variavel.startswith("%"):
        serie = nc.unit_share(df_base, "meio", modal_d)
        rotulo, un = f"% de uso — {modal_d}", "p.p."
    elif variavel.startswith("Mediana"):
        t = nc.tempo_stats_by(df_base[df_base["meio"] == modal_d], ["unidade"])
        serie = t.set_index("unidade")["Mediana"]
        rotulo, un = f"Mediana do tempo — {modal_d}", "min"
    else:
        serie = df_base[df_base["meio"] == modal_d].groupby("unidade")["pessoas"].sum()
        rotulo, un = f"Pessoas — {modal_d}", "pessoas"
    est = nc.descriptive_stats(serie)
    if not est:
        st.info("Sem dados para calcular.")
    else:
        tabela = pd.DataFrame({k: [v] for k, v in est.items() if not k.startswith("_")}).T
        tabela.columns = ["Valor"]
        tabela["Valor"] = tabela["Valor"].map(lambda v: "—" if pd.isna(v) else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        cA, cB = st.columns([1, 2])
        with cA:
            mostrar_tabela(tabela)
        with cB:
            fig = px.histogram(serie.reset_index(name="valor"), x="valor", nbins=20,
                               labels={"valor": f"{rotulo} ({un})"}, title="Histograma")
            fig.add_vline(x=est["Média"], line_dash="dash", annotation_text="média")
            fig.add_vline(x=est["Mediana"], line_dash="dot", annotation_text="mediana", annotation_position="bottom")
            mostrar_grafico(fig)
            fig = px.box(serie.reset_index(name="valor"), x="valor", points="all", hover_name=serie.index.name,
                         labels={"valor": f"{rotulo} ({un})"}, title="Boxplot (regra 1,5·IQR)")
            mostrar_grafico(fig)
        st.markdown(nc.interpretar(est, rotulo, un))
        out = est["_outliers"]
        if len(out):
            st.markdown("**Outliers:**")
            mostrar_tabela(out.sort_values(ascending=False).round(2).rename("valor").to_frame())

# --------------------------------------------------------------------------
# Aba 6 — Respostas às perguntas de negócio
# --------------------------------------------------------------------------
with abas[5]:
    st.subheader("Respostas às perguntas de negócio (atualizam com os filtros)")
    if usa_demo:
        st.warning("Os números abaixo são de demonstração. Com a base do IBGE, as respostas serão reais.")

    st.markdown("### 1) Mediana por meio de transporte e raça")
    if TEM_TEMPO and TEM_RACA:
        t = nc.tempo_stats_by(df_f, ["meio", "cor_raca"])
        alto, baixo = t.loc[t["Mediana"].idxmax()], t.loc[t["Mediana"].idxmin()]
        st.write(f"A maior mediana de tempo é de **{alto['cor_raca']}** em **{alto['meio']}** "
                 f"({alto['Mediana']:.1f} min); a menor é de **{baixo['cor_raca']}** em **{baixo['meio']}** "
                 f"({baixo['Mediana']:.1f} min). Diferenças entre raças dentro de um mesmo modal indicam "
                 "desigualdade de acesso/qualidade do deslocamento.")
    else:
        st.write("Mapeie raça e faixa de tempo para gerar esta resposta automaticamente.")

    st.markdown("### 2) Público × particular × ativo")
    st.write(f"**{pct.get('Público', 0):.1f}%** usam transporte público, **{pct.get('Particular', 0):.1f}%** "
             f"usam transporte particular (carro/moto) e **{pct.get('Ativo', 0):.1f}%** usam modais ativos "
             f"(bicicleta/a pé). O modal predominante é **{por_meio.index[0]}**.")

    st.markdown("### 3) Cidades com mais mobilidade ativa (bicicleta)")
    bici = next((m for m in df_base["meio"].unique() if "bicicleta" in m.lower()), None)
    if bici:
        top = nc.unit_share(df_base, "meio", bici).sort_values(ascending=False).head(3)
        st.write("Maiores percentuais de uso de bicicleta: " +
                 "; ".join(f"**{u}** ({v:.1f}%)" for u, v in top.items()) + ".")
    else:
        st.write("A base não possui a categoria bicicleta.")

    st.markdown("### Sugestão de leitura para as personas")
    st.markdown(
        "- **Fernando (nacional):** comparar a mediana de tempo entre raças e modais para priorizar investimento onde a desigualdade é maior.\n"
        "- **Ana, Luciene, Pedrinho e Lucas (cidades):** olhar o ranking de bicicleta e os outliers de tempo para "
        "definir ciclovias, corredores de ônibus e integração com o metrô.\n"
        "- **Média × mediana:** onde há outliers de tempo longo, a média superestima o deslocamento típico — decidir pela mediana.")

# --------------------------------------------------------------------------
# Aba 7 — Notícias e imagens
# --------------------------------------------------------------------------
with abas[6]:
    st.subheader("📰 Notícias e reportagens")
    noticias = [
        ("Automóvel é o meio de transporte mais utilizado no deslocamento para o trabalho", "Agência de Notícias IBGE",
         "Resultados do Censo 2022 sobre deslocamentos; destaca carro, ônibus, a pé e moto.",
         "https://agenciadenoticias.ibge.gov.br/agencia-noticias/noticias/44713-automovel-e-o-meio-de-transporte-mais-utilizado-no-deslocamento-para-o-trabalho",
         "Mobilidade"),
        ("Carro é o principal meio de transporte para o trabalho, diz Censo", "Agência Brasil",
         "Reportagem sobre o predomínio do automóvel e o tempo de deslocamento dos trabalhadores.",
         "https://agenciabrasil.ebc.com.br/geral/noticia/2025-10/carro-e-o-principal-meio-de-transporte-para-o-trabalho-diz-censo",
         "Mobilidade"),
        ("Mais pobres e pretos gastam mais tempo no transporte até o trabalho", "Acessa.com",
         "Conecta tempo de deslocamento, renda e raça — central para a persona.",
         "https://www.acessa.com/noticias/2025/10/287929-mais-pobres-e-pretos-gastam-mais-tempo-no-transporte-ate-o-trabalho-no-brasil.html",
         "Caos no trânsito / desigualdade"),
        ("Cidade de SP tem 152 mil moradores que levam mais de 2h para chegar ao trabalho", "Acessa.com",
         "Exemplo de gargalo extremo (outliers) e do peso do transporte coletivo nesses casos.",
         "https://www.acessa.com/noticias/2025/10/288012-cidade-de-sp-tem-152-mil-moradores-que-levam-mais-de-2h-para-chegar-ao-trabalho.html",
         "Caos no trânsito"),
        ("Carro é o principal meio de transporte para o trabalho, diz Censo", "Times Brasil",
         "Aponta relações entre tempo de trajeto e desigualdades sociais.",
         "https://timesbrasil.com.br/brasil/carro-e-o-principal-meio-de-transporte-para-o-trabalho-diz-censo/",
         "Mobilidade sustentável"),
        ("Censo 2022: como a população se desloca para estudar e trabalhar?", "IBGE Educa Jovens",
         "Material didático com os principais resultados do Censo sobre deslocamento.",
         "https://educa.ibge.gov.br/jovens/materias-especiais/23064-censo-2022-como-a-populacao-se-desloca-para-estudar-e-trabalhar.html",
         "Mobilidade sustentável"),
    ]
    for titulo, veiculo, resumo, url, tema in noticias:
        st.markdown(f"**[{titulo}]({url})**  \n_{veiculo} · {tema}_ — {resumo}")

    st.subheader("🖼️ Imagens ilustrativas")
    st.caption("Coloque fotos (grandes vias, ônibus, metrô, ciclovias) na pasta **imagens/** ao lado do app.py "
               "(.jpg/.png/.webp). O nome do arquivo vira a legenda. Prefira imagens livres (Wikimedia Commons, "
               "Unsplash, Pexels) e cite a fonte.")
    extras = st.file_uploader("…ou envie imagens agora", type=["jpg", "jpeg", "png", "webp"],
                              accept_multiple_files=True, key="imgs")
    arquivos = sorted(p for p in PASTA_IMAGENS.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}) \
        if PASTA_IMAGENS.exists() else []
    imagens = [(p.stem.replace("_", " "), str(p)) for p in arquivos] + [(f.name, f) for f in extras]
    if imagens:
        cols = st.columns(3)
        for i, (legenda, fonte) in enumerate(imagens):
            cols[i % 3].image(fonte, caption=legenda)
    else:
        st.info("Nenhuma imagem encontrada ainda. Adicione arquivos na pasta imagens/ para completar esta seção.")

# --------------------------------------------------------------------------
# Aba 8 — Fonte e método
# --------------------------------------------------------------------------
with abas[7]:
    st.subheader("Fonte, método e premissas")
    st.markdown(
        "**Fonte:** IBGE — Censo Demográfico 2022, *Deslocamentos para trabalho e para estudo* (resultados "
        "preliminares da amostra), via SIDRA. Pessoas ocupadas que trabalham fora do domicílio.\n\n"
        "**Tratamento (ETL):** colunas renomeadas pelo mapeamento; valores como '-', 'X' e '...' viram vazio; "
        "linhas 'Total' são removidas para não duplicar contagens; UF/região padronizadas.\n\n"
        "**Medidas:** média, mediana, moda, quartis, IQR = Q3 − Q1, amplitude, variância e desvio padrão (amostral, "
        "n−1); outliers pela regra 1,5·IQR. Para o tempo, que vem em **faixas**, os quartis usam interpolação linear "
        "dentro da classe: Q = L + ((p·N − F_ant)/f)·h.\n\n"
        "**Premissas:** a faixa aberta (“mais de 2 horas”) foi limitada a 180 min (editável); a classificação em "
        "público/particular/ativo é editável; o filtro de modal não altera os percentuais de uso.")
    st.markdown("**Referência nacional (Censo 2022, % por meio de transporte principal no trajeto ao trabalho) "
                "— use para conferir sua base:**")
    ref = pd.DataFrame({
        "Meio": ["Automóvel", "Ônibus", "A pé", "Motocicleta"],
        "Brasil": [32.3, 21.4, 17.8, 16.4],
        "Branca": [42.9, 17.6, 15.7, 13.6],
        "Preta": [21.0, 29.5, 19.8, np.nan],
        "Amarela": [56.1, np.nan, np.nan, np.nan],
    })
    mostrar_tabela(ref)
    st.caption("Fonte dos percentuais: Agência de Notícias do IBGE. Células vazias = valor não conferido.")
