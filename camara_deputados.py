# -*- coding: utf-8 -*-
"""
camara_deputados.py

Aplica o índice de assortatividade multi-categoria fuzzy (r_dp, s_fuzzy)
à Câmara dos Deputados brasileira: cada deputado recebe graus de
pertinência fuzzy a três grupos -- Governo, Oposição e Centrão --
calculados a partir do seu alinhamento com as orientações de voto do
governo, DENTRO de cada mandato. A rede é a de coautoria de proposições
legislativas (dois deputados são ligados por uma aresta cujo peso é o
número de proposições que assinaram juntos).

Segue a mesma estrutura dos demais scripts do repositório
(deezer_analise.py, coautoria_crisp_com_peso.py): funções de
similaridade, S_obs, S_esp (Monte Carlo) e r_dp = (S_obs - S_esp) / dp,
com IC 95% aproximado por r_dp +- 1.96/sqrt(N_AMOSTRAS). Acrescenta um
teste de permutação como checagem de robustez complementar ao IC.

Dados esperados em PASTA, um trio de arquivos por ano:
    votacoesVotos-{ano}.xlsx
    votacoesOrientacoes-{ano}.xlsx
    proposicoesAutores-{ano}.xlsx
Disponíveis em https://dadosabertos.camara.leg.br/.
"""

import os
import math
import random
import statistics
from collections import defaultdict
from itertools import combinations

import pandas as pd
import networkx as nx

PASTA         = '/content/sample_data/camara_deputados'
N_AMOSTRAS    = 10_000
N_PERMUTACOES = 2_000
SEMENTE       = 42

# Blocos de mandato. 2016 fica isolado por ser o ano de transição do
# impeachment -- nem colado em 2015 (Dilma) nem em 2017-2018 (Temer).
MANDATOS = {
    '2003-2006':                  [2003, 2004, 2005, 2006],
    '2007-2010':                  [2007, 2008, 2009, 2010],
    '2011-2014':                  [2011, 2012, 2013, 2014],
    '2015 (Dilma)':               [2015],
    '2016 (transição)':           [2016],
    '2017-2018 (Temer)':          [2017, 2018],
    '2019-2022':                  [2019, 2020, 2021, 2022],
    '2023-2025 (atual, parcial)': [2023, 2024, 2025],
}


# ── 1. Alinhamento com o governo: P_f (favor) e P_c (contra) ────────────
def carregar_favor_contra(pasta, anos):
    """Concatena os anos do período e devolve {deputado_id: proporção}
    de votos a favor/contra a orientação do governo, sobre o total de
    votações válidas do período inteiro (recontagem agregada, não média
    de percentuais anuais -- evita distorcer anos com poucas votações)."""
    vs, ors = [], []
    for ano in anos:
        fv = os.path.join(pasta, f'votacoesVotos-{ano}.xlsx')
        fo = os.path.join(pasta, f'votacoesOrientacoes-{ano}.xlsx')
        if os.path.exists(fv) and os.path.exists(fo):
            vs.append(pd.read_excel(fv))
            ors.append(pd.read_excel(fo))
    if not vs:
        return {}, {}

    votos, orient = pd.concat(vs, ignore_index=True), pd.concat(ors, ignore_index=True)
    gov = orient[orient.siglaBancada.isin(['Governo', 'GOV.']) & orient.orientacao.isin(['Sim', 'Não'])]
    gov = gov[['idVotacao', 'orientacao']].rename(columns={'orientacao': 'orientacao_governo'})
    total_votacoes = gov.idVotacao.nunique()
    if total_votacoes == 0:
        return {}, {}

    deputados = votos.deputado_id.unique()
    base = pd.MultiIndex.from_product(
        [deputados, gov.idVotacao], names=['deputado_id', 'idVotacao']
    ).to_frame(index=False)
    base = base.merge(gov, on='idVotacao', how='left')
    base = base.merge(votos[['idVotacao', 'deputado_id', 'voto']], on=['idVotacao', 'deputado_id'], how='left')

    base['favor']  = base.voto.isin(['Sim', 'Não']) & (base.voto == base.orientacao_governo)
    base['contra'] = base.voto.isin(['Sim', 'Não']) & (base.voto != base.orientacao_governo)

    r = base.groupby('deputado_id').agg(favor=('favor', 'sum'), contra=('contra', 'sum'))
    return (r.favor / total_votacoes).to_dict(), (r.contra / total_votacoes).to_dict()


# ── 2. Pertinências fuzzy: trapézio relativo ao mandato + AND de Zadeh ──
def calcular_limiares(pct_favor, pct_contra):
    """p50/p75 de P_f e P_c, calculados sobre os deputados DESSE
    mandato -- 'ser Governo' é relativo ao Congresso daquele período,
    não a uma régua fixa global."""
    fav, con = pd.Series(pct_favor), pd.Series(pct_contra)
    return {'favor_p50': fav.quantile(0.50), 'favor_p75': fav.quantile(0.75),
            'contra_p50': con.quantile(0.50), 'contra_p75': con.quantile(0.75)}


def _trapezio(valor, inf, sup):
    if sup <= inf:
        return 1.0 if valor >= sup else 0.0
    if valor <= inf:
        return 0.0
    if valor >= sup:
        return 1.0
    return (valor - inf) / (sup - inf)


def pertinencias_trapezoidais(pct_favor, pct_contra, limiares):
    """mu_Governo = trapézio em P_f; mu_Oposição = trapézio em P_c;
    mu_Centrão = min(1 - mu_Governo, 1 - mu_Oposição), o AND fuzzy de
    Zadeh aplicado aos dois complementos."""
    x = _trapezio(pct_favor, limiares['favor_p50'], limiares['favor_p75'])
    z = _trapezio(pct_contra, limiares['contra_p50'], limiares['contra_p75'])
    return {'Governo': x, 'Oposição': z, 'Centrão': min(1 - x, 1 - z)}


# ── 3. Similaridade fuzzy (mesma Eq. s_fuzzy usada em cocitacao_fuzzy.py) ─
def s_fuzzy(mu_i, mu_j):
    return max(mu_i[c] * mu_j[c] for c in ('Governo', 'Oposição', 'Centrão'))


# ── 4. Rede de coautoria de proposições, com corte global de outliers ──
def calcular_max_autores_global(pasta, todos_os_anos):
    """Corte de outliers (percentil 99 de autores/proposição) calculado
    UMA VEZ sobre toda a base 2003-2025 -- não por mandato -- para que o
    critério de 'proposição normal' não mude de tamanho a cada período e
    as redes continuem estruturalmente comparáveis entre si (ex.: PECs,
    que exigem assinatura de 1/3 da Câmara, aparecem em todos os
    mandatos, mas só distorcem a densidade se o corte for relativo)."""
    partes = [pd.read_excel(f) for ano in todos_os_anos
              if os.path.exists(f := os.path.join(pasta, f'proposicoesAutores-{ano}.xlsx'))]
    dep = pd.concat(partes, ignore_index=True)
    dep = dep[(dep.codTipoAutor == 10000) & dep.idDeputadoAutor.notna()].copy()
    dep['idDeputadoAutor'] = dep['idDeputadoAutor'].astype(int)
    n_autores = dep.groupby('idProposicao')['idDeputadoAutor'].nunique()
    return n_autores.quantile(0.99)


def construir_rede(pasta, anos, attrs_todos, max_autores):
    """attrs_todos: {deputado_id: pertinências}, já calculado antes de
    chamar esta função. max_autores: corte global (ver acima)."""
    partes = [pd.read_excel(f) for ano in anos
              if os.path.exists(f := os.path.join(pasta, f'proposicoesAutores-{ano}.xlsx'))]
    if not partes:
        return nx.Graph(), {}

    dep = pd.concat(partes, ignore_index=True)
    dep = dep[(dep.codTipoAutor == 10000) & dep.idDeputadoAutor.notna()].copy()
    dep['idDeputadoAutor'] = dep['idDeputadoAutor'].astype(int)
    por_prop = dep.groupby('idProposicao')['idDeputadoAutor'].apply(lambda s: sorted(set(s)))

    pesos = defaultdict(int)
    for autores in por_prop:
        if 2 <= len(autores) <= max_autores:
            for a, b in combinations(autores, 2):
                pesos[(a, b)] += 1

    G = nx.Graph()
    for (a, b), w in pesos.items():
        G.add_edge(a, b, peso=w)

    attrs = {n: attrs_todos[n] for n in G.nodes() if n in attrs_todos}
    G.remove_nodes_from([n for n in G.nodes() if n not in attrs])
    G.remove_nodes_from(list(nx.isolates(G)))
    return G, attrs


# ── 5. S_obs, S_esp (Monte Carlo), r_dp e IC 95% ────────────────────────
def calcular_s_obs(G, attrs, func):
    sim = peso = 0.0
    for u, v, d in G.edges(data=True):
        w = d.get('peso', 1)
        sim += w * func(attrs[u], attrs[v])
        peso += w
    return sim / peso if peso else 0.0


def estimar_s_esp(G, attrs, func, n=N_AMOSTRAS):
    """Modelo nulo: sorteia pares proporcional à força (soma dos pesos
    das arestas do nó), coerente com o modelo de configuração ponderado."""
    random.seed(SEMENTE)
    nos    = list(G.nodes())
    forcas = [sum(d.get('peso', 1) for _, _, d in G.edges(no, data=True)) for no in nos]
    cats   = [attrs[no] for no in nos]
    amostras = []
    while len(amostras) < n:
        i = random.choices(range(len(nos)), weights=forcas)[0]
        j = random.choices(range(len(nos)), weights=forcas)[0]
        if i != j:
            amostras.append(func(cats[i], cats[j]))
    return statistics.mean(amostras), statistics.stdev(amostras)


def calcular_r(S_obs, S_esp, dp, n=N_AMOSTRAS):
    """r_dp = (S_obs - S_esp) / dp  |  IC 95%: r_dp +- 1.96/sqrt(n)."""
    if dp <= 0:
        return 0.0, 0.0, 0.0
    r = (S_obs - S_esp) / dp
    m = 1.96 / math.sqrt(n)
    return r, r - m, r + m


# ── 6. Teste de permutação (robustez extra: H0 = atributo não importa) ──
def teste_permutacao(G, attrs, func, n_perm=N_PERMUTACOES):
    """Embaralha as pertinências entre os nós, mantendo a rede fixa, e
    recalcula S_obs - S_esp a cada permutação. p-valor = fração de
    permutações cuja diferença é, em módulo, tão extrema quanto a real."""
    random.seed(SEMENTE)
    nos, valores = list(attrs.keys()), list(attrs.values())

    def diferenca(attrs_rotulo):
        s_obs = calcular_s_obs(G, attrs_rotulo, func)
        s_esp, _ = estimar_s_esp(G, attrs_rotulo, func, n=1000)  # amostra menor: só para o teste
        return s_obs - s_esp

    d_real = diferenca(attrs)
    excedidas = 0
    for _ in range(n_perm):
        random.shuffle(valores)
        if abs(diferenca(dict(zip(nos, valores)))) >= abs(d_real):
            excedidas += 1
    return excedidas / n_perm


# ── 7. Pipeline por mandato ──────────────────────────────────────────────
def analisar_mandato(pasta, rotulo, anos, max_autores):
    pct_favor, pct_contra = carregar_favor_contra(pasta, anos)
    if not pct_favor:
        print(f"  [aviso] {rotulo}: sem votações válidas de governo -- pulando")
        return None

    limiares = calcular_limiares(pct_favor, pct_contra)
    attrs_todos = {d: pertinencias_trapezoidais(pct_favor[d], pct_contra[d], limiares)
                   for d in pct_favor}

    G, attrs = construir_rede(pasta, anos, attrs_todos, max_autores)
    if G.number_of_edges() == 0:
        print(f"  [aviso] {rotulo}: rede sem arestas -- pulando")
        return None

    S_obs = calcular_s_obs(G, attrs, s_fuzzy)
    S_esp, dp = estimar_s_esp(G, attrs, s_fuzzy)
    r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp)
    p_perm = teste_permutacao(G, attrs, s_fuzzy)

    return {
        'periodo': rotulo,
        'n_nos': G.number_of_nodes(), 'n_arestas': G.number_of_edges(),
        'S_obs': round(S_obs, 4), 'S_esp': round(S_esp, 4), 'dp': round(dp, 4),
        'r_dp': round(r, 4), 'ic_inf': round(ic_inf, 4), 'ic_sup': round(ic_sup, 4),
        'p_permutacao': round(p_perm, 4),
    }


# ── Execução ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    todos_os_anos = sorted({a for anos in MANDATOS.values() for a in anos})
    max_autores_global = calcular_max_autores_global(PASTA, todos_os_anos)
    print(f"Corte global de outliers (p99 autores/proposição, 2003-2025): {max_autores_global:.0f}")

    resultados = [r for rotulo, anos in MANDATOS.items()
                  if (r := analisar_mandato(PASTA, rotulo, anos, max_autores_global))]

    df = pd.DataFrame(resultados)
    print(f"\n{'=' * 100}")
    print("  Assortatividade fuzzy (Governo/Oposição/Centrão) por mandato")
    print(f"{'=' * 100}")
    print(df.to_string(index=False))
    df.to_csv('assortatividade_camara_por_mandato.csv', index=False)
    print("\nTabela salva em assortatividade_camara_por_mandato.csv")
