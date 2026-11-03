"""
nucleo.py — lógica de dados e estatística do dashboard "Transporte e Mobilidade Urbana".

Não depende do Streamlit: pode ser testado separadamente e é a parte que a
Profa. Conceição pode conferir (cálculo de mediana/quartis para dados agrupados,
estatística descritiva, regra 1,5·IQR).

Colunas canônicas usadas no app:
    uf, regiao, municipio, cor_raca, meio, renda, faixa_tempo, pessoas
"""
from __future__ import annotations

import io
import re
import unicodedata

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
UF_INFO = {
    "AC": ("Acre", "Norte"), "AL": ("Alagoas", "Nordeste"), "AP": ("Amapá", "Norte"),
    "AM": ("Amazonas", "Norte"), "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"),
    "DF": ("Distrito Federal", "Centro-Oeste"), "ES": ("Espírito Santo", "Sudeste"),
    "GO": ("Goiás", "Centro-Oeste"), "MA": ("Maranhão", "Nordeste"),
    "MT": ("Mato Grosso", "Centro-Oeste"), "MS": ("Mato Grosso do Sul", "Centro-Oeste"),
    "MG": ("Minas Gerais", "Sudeste"), "PA": ("Pará", "Norte"), "PB": ("Paraíba", "Nordeste"),
    "PR": ("Paraná", "Sul"), "PE": ("Pernambuco", "Nordeste"), "PI": ("Piauí", "Nordeste"),
    "RJ": ("Rio de Janeiro", "Sudeste"), "RN": ("Rio Grande do Norte", "Nordeste"),
    "RS": ("Rio Grande do Sul", "Sul"), "RO": ("Rondônia", "Norte"), "RR": ("Roraima", "Norte"),
    "SC": ("Santa Catarina", "Sul"), "SP": ("São Paulo", "Sudeste"),
    "SE": ("Sergipe", "Nordeste"), "TO": ("Tocantins", "Norte"),
}

CANONICAS = {
    "uf": "Unidade da Federação (UF)",
    "regiao": "Região",
    "municipio": "Município",
    "cor_raca": "Cor ou raça",
    "meio": "Meio de transporte",
    "renda": "Categoria de renda",
    "faixa_tempo": "Faixa de tempo de deslocamento",
    "pessoas": "Valor (nº de pessoas)",
}

GRUPOS = ["Público", "Particular", "Ativo", "Outros"]

FAIXAS_TEMPO_PADRAO = [
    "Até 5 minutos",
    "De 6 minutos até meia hora",
    "Mais de meia hora até uma hora",
    "Mais de uma hora até duas horas",
    "Mais de duas horas",
]


# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------
def _norm(texto) -> str:
    """minúsculas, sem acentos, sem espaços extras."""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


_NOME_PARA_SIGLA = {_norm(nome): sigla for sigla, (nome, _) in UF_INFO.items()}
_NOME_PARA_SIGLA.update({sigla.lower(): sigla for sigla in UF_INFO})


def uf_para_sigla(valor) -> str:
    """'Minas Gerais' -> 'MG'; 'mg' -> 'MG'; desconhecido -> valor original."""
    return _NOME_PARA_SIGLA.get(_norm(valor), str(valor).strip())


# --------------------------------------------------------------------------
# Faixas de tempo (dados agrupados)
# --------------------------------------------------------------------------
_PALAVRAS_TEMPO = [
    ("meia hora", "30 min"), ("uma hora", "60 min"), ("duas horas", "120 min"),
    ("tres horas", "180 min"), ("quatro horas", "240 min"),
]


def parse_faixa(rotulo) -> tuple[float, float]:
    """
    Converte o rótulo de uma faixa de tempo em (mínimo, máximo) em minutos.
    Ex.: 'Até 5 minutos' -> (0, 5); 'De 6 minutos até meia hora' -> (6, 30);
         'Mais de duas horas' -> (120, 180)  (limite superior assumido).
    O app permite ao usuário corrigir esses limites manualmente.
    """
    s = _norm(rotulo)
    for palavra, num in _PALAVRAS_TEMPO:
        s = s.replace(palavra, num)
    achados = re.findall(r"(\d+(?:[.,]\d+)?)\s*(horas?|hs?|min(?:utos?)?)?", s)
    if not achados:
        return (np.nan, np.nan)
    # unidade ausente herda a do próximo número ("6 a 30 min"); padrão = minutos
    unidades, proxima = [], "min"
    for _, un in reversed(achados):
        proxima = un if un else proxima
        unidades.append(proxima)
    unidades.reverse()
    valores = []
    for (num, _), un in zip(achados, unidades):
        v = float(num.replace(",", "."))
        valores.append(v * 60 if un.startswith("h") else v)
    if len(valores) >= 2:
        return (min(valores[:2]), max(valores[:2]))
    v = valores[0]
    if re.search(r"\b(ate|menos de|ate)\b", s):
        return (0.0, v)
    if re.search(r"\b(mais de|acima|superior|maior)\b", s):
        return (v, v + 60.0)
    return (v, v)


def grouped_quantile(los, his, counts, p: float) -> float:
    """
    Quantil de dados agrupados em classes (interpolação linear dentro da classe):
        Q_p = L + ((p·N − F_ant) / f) · h
    L = limite inferior da classe, F_ant = frequência acumulada anterior,
    f = frequência da classe, h = amplitude da classe.  p=0,5 dá a mediana.
    """
    los = np.asarray(los, dtype=float)
    his = np.asarray(his, dtype=float)
    counts = np.asarray(counts, dtype=float)
    ok = np.isfinite(los) & np.isfinite(his) & np.isfinite(counts) & (counts > 0)
    if not ok.any():
        return float("nan")
    los, his, counts = los[ok], his[ok], counts[ok]
    ordem = np.argsort(los, kind="stable")
    los, his, counts = los[ordem], his[ordem], counts[ordem]
    acum = np.cumsum(counts)
    alvo = p * acum[-1]
    i = min(int(np.searchsorted(acum, alvo, side="left")), len(counts) - 1)
    anterior = acum[i] - counts[i]
    return float(los[i] + (alvo - anterior) / counts[i] * (his[i] - los[i]))


def tempo_stats_by(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """
    Q1, mediana, Q3, IQR (em minutos) do tempo de deslocamento por grupo,
    usando dados agrupados em faixas. Requer colunas _lo, _hi e pessoas.
    Também devolve Min/Max (limites das faixas ocupadas) e o nº de pessoas.
    """
    d = df.dropna(subset=["_lo", "_hi"]).copy()
    cols = list(group_cols)
    if not cols:
        d["_todos"] = "Todos"
        cols = ["_todos"]
    agg = d.groupby(cols + ["_lo", "_hi"], observed=True, as_index=False)["pessoas"].sum()
    linhas = []
    for chave, g in agg.groupby(cols, observed=True):
        chave = chave if isinstance(chave, tuple) else (chave,)
        lo, hi, c = g["_lo"].to_numpy(), g["_hi"].to_numpy(), g["pessoas"].to_numpy()
        q1 = grouped_quantile(lo, hi, c, 0.25)
        q2 = grouped_quantile(lo, hi, c, 0.50)
        q3 = grouped_quantile(lo, hi, c, 0.75)
        usadas = c > 0
        linhas.append((*chave, q1, q2, q3, q3 - q1,
                       lo[usadas].min() if usadas.any() else np.nan,
                       hi[usadas].max() if usadas.any() else np.nan,
                       c.sum()))
    out = pd.DataFrame(linhas, columns=cols + ["Q1", "Mediana", "Q3", "IQR", "Min", "Max", "Pessoas"])
    if group_cols == []:
        out = out.drop(columns=["_todos"])
    return out


# --------------------------------------------------------------------------
# Classificação dos meios de transporte
# --------------------------------------------------------------------------
def classificar_meio(rotulo) -> str:
    """Público / Particular / Ativo / Outros (editável no app)."""
    s = _norm(rotulo)
    palavras = set(re.findall(r"[a-z]+", s))
    if "bicicleta" in s or "bike" in s or s in {"a pe", "pe"} or "caminhada" in s:
        return "Ativo"
    if (any(k in s for k in ("onibus", "brt", "metro", "trem", "lotacao", "barca", "coletivo"))
            or palavras & {"van", "perua"}):
        return "Público"
    if any(k in s for k in ("automovel", "carro", "moto", "taxi", "aplicativo")):
        return "Particular"
    return "Outros"


# --------------------------------------------------------------------------
# Estatística descritiva (para vetores de UFs/municípios)
# --------------------------------------------------------------------------
def descriptive_stats(valores) -> dict:
    """Média, mediana, moda, quartis, IQR, amplitude, variância, desvio e outliers (1,5·IQR)."""
    x = pd.Series(valores, dtype="float64").dropna()
    n = len(x)
    if n == 0:
        return {}
    q1, q2, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    lim_inf, lim_sup = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = x[(x < lim_inf) | (x > lim_sup)]
    vc = x.round(1).value_counts()
    moda = np.nan if vc.iloc[0] == 1 else float(vc[vc == vc.max()].index.min())
    return {
        "n": n,
        "Média": float(x.mean()),
        "Mediana": float(q2),
        "Moda": moda,
        "Q1": float(q1),
        "Q3": float(q3),
        "IQR": float(iqr),
        "Amplitude": float(x.max() - x.min()),
        "Mínimo": float(x.min()),
        "Máximo": float(x.max()),
        "Variância": float(x.var(ddof=1)) if n > 1 else np.nan,
        "Desvio padrão": float(x.std(ddof=1)) if n > 1 else np.nan,
        "Limite inferior (Q1−1,5·IQR)": float(lim_inf),
        "Limite superior (Q3+1,5·IQR)": float(lim_sup),
        "Qtd. de outliers": int(len(outliers)),
        "_outliers": outliers,
    }


def interpretar(stats: dict, rotulo: str, unidade: str = "") -> str:
    """Texto interpretativo automático (média × mediana, dispersão, outliers)."""
    if not stats:
        return "Sem dados suficientes para interpretar."
    u = f" {unidade}" if unidade else ""
    media, med = stats["Média"], stats["Mediana"]
    dif = media - med
    escala = abs(med) if med else 1.0
    if abs(dif) / escala < 0.05:
        forma = (f"A média ({media:.1f}{u}) e a mediana ({med:.1f}{u}) são muito próximas: "
                 "a distribuição é aproximadamente simétrica.")
    elif dif > 0:
        forma = (f"A média ({media:.1f}{u}) está acima da mediana ({med:.1f}{u}): há assimetria à direita; "
                 "valores muito altos puxam a média para cima, por isso a mediana é a melhor medida de centro.")
    else:
        forma = (f"A média ({media:.1f}{u}) está abaixo da mediana ({med:.1f}{u}): há assimetria à esquerda; "
                 "valores muito baixos puxam a média para baixo, por isso a mediana é mais representativa.")
    cv = stats["Desvio padrão"] / media * 100 if media else np.nan
    disp = (f" O IQR é {stats['IQR']:.1f}{u} (metade central dos dados) e o desvio padrão é "
            f"{stats['Desvio padrão']:.1f}{u}" + (f" (coeficiente de variação ≈ {cv:.0f}%)." if np.isfinite(cv) else "."))
    q = stats["Qtd. de outliers"]
    if q == 0:
        out = " Pela regra 1,5·IQR, não há outliers: o comportamento é relativamente homogêneo."
    else:
        out = (f" Pela regra 1,5·IQR há {q} outlier(s) (fora de "
               f"[{stats['Limite inferior (Q1−1,5·IQR)']:.1f}; {stats['Limite superior (Q3+1,5·IQR)']:.1f}]{u}); "
               "eles afetam a média mais do que a mediana.")
    return f"**{rotulo}.** " + forma + disp + out


# --------------------------------------------------------------------------
# Leitura de arquivos e ETL
# --------------------------------------------------------------------------
def read_uploaded(dados: bytes, nome: str, skiprows: int = 0) -> pd.DataFrame:
    """Lê CSV (separador e codificação detectados) ou XLSX exportado do SIDRA."""
    if nome.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(dados), skiprows=skiprows)
    ultimo = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        for sep in (None, ";", ","):
            try:
                df = pd.read_csv(io.BytesIO(dados), sep=sep, engine="python",
                                 encoding=enc, skiprows=skiprows)
                if df.shape[1] >= 2:
                    return df
            except Exception as e:  # tenta a próxima combinação
                ultimo = e
    raise ValueError(f"Não foi possível ler o arquivo: {ultimo}")


_DICAS = {
    "pessoas": ["valor", "pessoas", "quantidade", "total de", "numero"],
    "faixa_tempo": ["tempo"],
    "meio": ["meio de transporte", "meio", "modal", "transporte"],
    "cor_raca": ["cor ou raca", "raca", "cor"],
    "renda": ["rendimento", "renda"],
    "municipio": ["municipio", "cidade"],
    "uf": ["unidade da federacao", "uf", "estado"],
    "regiao": ["regiao", "grande regiao"],
}


def adivinhar_mapeamento(colunas) -> dict:
    """Sugere qual coluna do arquivo corresponde a cada coluna canônica."""
    usadas, mapa = set(), {}
    normais = {c: _norm(c) for c in colunas}
    for canon in ["pessoas", "faixa_tempo", "meio", "cor_raca", "renda", "municipio", "uf", "regiao"]:
        mapa[canon] = None
        for dica in _DICAS[canon]:
            achou = [c for c, n in normais.items() if c not in usadas and (n == dica or dica in n.split() or dica in n)]
            if canon == "meio":
                achou = [c for c in achou if "tempo" not in normais[c]]
            if achou:
                mapa[canon] = achou[0]
                usadas.add(achou[0])
                break
    return mapa


def _limpar_numero(serie: pd.Series) -> pd.Series:
    """Converte para número; '-', 'X', '...' viram vazio; '12,5' vira 12.5."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")
    s = serie.astype(str).str.strip()
    milhar = s.str.fullmatch(r"\d{1,3}(\.\d{3})+")          # 1.234.567 (pt-BR) -> 1234567
    s = s.mask(milhar, s.str.replace(".", "", regex=False))
    so_virgula = s.str.contains(",", regex=False) & ~s.str.contains(".", regex=False)
    s = s.mask(so_virgula, s.str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def prepare(raw: pd.DataFrame, mapa: dict, remover_totais: bool = True) -> pd.DataFrame:
    """
    ETL: renomeia para colunas canônicas, converte números ('-', 'X', '...' viram vazio),
    remove linhas 'Total' (evita dupla contagem), padroniza UF/região e cria 'unidade' e 'grupo'.
    """
    cols = {canon: col for canon, col in mapa.items() if col and col in raw.columns}
    if "pessoas" not in cols:
        raise ValueError("Informe qual coluna contém o valor (nº de pessoas).")
    df = raw[list(cols.values())].copy()
    df.columns = list(cols.keys())
    df["pessoas"] = _limpar_numero(df["pessoas"])
    df = df.dropna(subset=["pessoas"])
    df = df[df["pessoas"] >= 0]

    for c in [c for c in df.columns if c != "pessoas"]:
        df[c] = df[c].astype(str).str.strip()
        if remover_totais:
            totais = {"total", "total geral"}
            if c in ("uf", "municipio", "regiao"):
                totais = totais | {"brasil"}
            df = df[~df[c].map(_norm).isin(totais)]

    # "Belo Horizonte (MG)" -> UF = MG
    if "municipio" in df.columns and "uf" not in df.columns:
        sig = df["municipio"].str.extract(r"\(([A-Za-z]{2})\)\s*$")[0]
        if sig.notna().mean() > 0.5:
            df["uf"] = sig.str.upper()
            df["municipio"] = df["municipio"].str.replace(r"\s*\([A-Za-z]{2}\)\s*$", "", regex=True)
    if "uf" in df.columns:
        df["uf"] = df["uf"].map(uf_para_sigla)
        if "regiao" not in df.columns:
            df["regiao"] = df["uf"].map(lambda s: UF_INFO.get(s, (None, "Não identificada"))[1])
    if "municipio" in df.columns:
        df["unidade"] = df["municipio"]
    elif "uf" in df.columns:
        df["unidade"] = df["uf"]
    else:
        df["unidade"] = "Brasil"
    if "meio" in df.columns:
        df["grupo"] = df["meio"].map(classificar_meio)
    return df.reset_index(drop=True)


def faixa_table(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela editável (faixa, mín, máx em minutos) com limites sugeridos automaticamente."""
    rotulos = pd.Series(df["faixa_tempo"].unique())
    t = pd.DataFrame({"faixa": rotulos})
    lims = t["faixa"].map(parse_faixa)
    t["min_min"] = [a for a, _ in lims]
    t["max_min"] = [b for _, b in lims]
    return t.sort_values(["min_min", "max_min"], na_position="last").reset_index(drop=True)


def apply_faixas(df: pd.DataFrame, tabela: pd.DataFrame) -> pd.DataFrame:
    """Anexa _lo/_hi (limites da faixa em minutos) a cada linha."""
    m = tabela.rename(columns={"faixa": "faixa_tempo", "min_min": "_lo", "max_min": "_hi"})
    return df.merge(m[["faixa_tempo", "_lo", "_hi"]], on="faixa_tempo", how="left")


def unit_share(df: pd.DataFrame, coluna: str, valor: str, unidade: str = "unidade") -> pd.Series:
    """% de pessoas com df[coluna] == valor em cada unidade (denominador = todas as pessoas da unidade)."""
    tot = df.groupby(unidade)["pessoas"].sum()
    sel = df[df[coluna] == valor].groupby(unidade)["pessoas"].sum()
    return (sel.reindex(tot.index).fillna(0) / tot * 100).rename("percentual")


# --------------------------------------------------------------------------
# Dados FICTÍCIOS de demonstração (apenas para testar o app sem arquivo)
# --------------------------------------------------------------------------
def generate_demo(seed: int = 42) -> pd.DataFrame:
    """
    Gera uma base sintética no formato que o app espera.
    ATENÇÃO: NÃO são dados do IBGE. Servem só para ver o dashboard funcionando.
    """
    rng = np.random.default_rng(seed)
    meios = ["A pé", "Bicicleta", "Motocicleta", "Automóvel", "Ônibus",
             "BRT ou ônibus de trânsito rápido", "Trem ou metrô", "Van, perua ou assemelhados"]
    base = np.array([17.8, 3.0, 16.4, 32.3, 21.4, 0.8, 1.6, 1.5])
    racas = ["Branca", "Preta", "Amarela", "Parda", "Indígena"]
    peso_raca = np.array([0.43, 0.10, 0.01, 0.45, 0.01])
    mod_raca = {
        "Branca":   [0.9, 0.8, 0.85, 1.3, 0.8, 0.8, 0.9, 0.9],
        "Preta":    [1.1, 1.0, 1.0, 0.65, 1.4, 1.2, 1.2, 1.1],
        "Amarela":  [0.8, 0.7, 0.7, 1.7, 0.7, 0.7, 0.9, 0.8],
        "Parda":    [1.0, 1.2, 1.1, 0.8, 1.05, 1.0, 0.9, 1.0],
        "Indígena": [1.8, 1.5, 0.8, 0.5, 0.7, 0.3, 0.2, 0.6],
    }
    rendas = ["Até 1/2 salário mínimo", "Mais de 1/2 a 1 salário mínimo",
              "Mais de 1 a 2 salários mínimos", "Mais de 2 salários mínimos"]
    peso_renda = np.array([0.25, 0.30, 0.30, 0.15])
    mod_renda = [[1.3, 1.3, 0.6, 0.4, 1.2, 1.0, 0.9, 1.0],
                 [1.1, 1.1, 0.9, 0.7, 1.2, 1.0, 1.0, 1.0],
                 [0.9, 0.9, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0],
                 [0.6, 0.7, 0.9, 1.9, 0.5, 0.8, 1.2, 0.8]]
    faixas = FAIXAS_TEMPO_PADRAO
    tempo_base = np.array([
        [.35, .50, .12, .025, .005], [.12, .60, .22, .05, .01], [.08, .62, .24, .05, .01],
        [.07, .55, .30, .07, .01], [.03, .33, .40, .19, .05], [.02, .30, .40, .20, .08],
        [.01, .20, .42, .27, .10], [.03, .35, .40, .18, .04]])

    municipios = [(uf, f"Município {uf}-{i}") for uf in UF_INFO for i in (1, 2, 3)]
    idx_bike = set(rng.choice(len(municipios), 4, replace=False))      # outliers de bicicleta
    idx_metro = {m for m, (uf, _) in enumerate(municipios) if uf in ("SP", "RJ") and m % 3 == 0}

    linhas = []
    for m, (uf, nome) in enumerate(municipios):
        pop = float(rng.lognormal(mean=10.8, sigma=0.7))                # trabalhadores (fictício)
        ruido = rng.lognormal(0, 0.35, size=len(meios))
        if m in idx_bike:
            ruido[1] *= 3.5
        congest = 1.0 + 0.25 * rng.random() + (0.5 if m in idx_metro else 0.0)
        for r in racas:
            for j, rd in enumerate(rendas):
                v = base * ruido * np.array(mod_raca[r]) * np.array(mod_renda[j])
                v = v / v.sum()
                k = congest * (1.1 if r in ("Preta", "Parda") else 1.0) * (1.1 if j == 0 else 1.0)
                for a, meio in enumerate(meios):
                    p = tempo_base[a] * k ** np.arange(5)
                    p = p / p.sum()
                    n = pop * peso_raca[racas.index(r)] * peso_renda[j] * v[a] * p
                    for b, faixa in enumerate(faixas):
                        linhas.append((uf, UF_INFO[uf][1], nome, r, meio, rd, faixa, int(round(n[b]))))
    return pd.DataFrame(linhas, columns=["uf", "regiao", "municipio", "cor_raca", "meio",
                                         "renda", "faixa_tempo", "pessoas"])
