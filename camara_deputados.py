# -*- coding: utf-8 -*-
"""
camara_deputados.py

Aplicação à Câmara dos Deputados brasileira. Cada deputado recebe graus
de pertinência fuzzy a três grupos — Governo, Oposição e Centrão —
calculados a partir do seu alinhamento com as orientações de voto do
governo, dentro de cada mandato (os limiares são recalculados por
período, não fixos globalmente). A rede é a de coautoria de proposições
legislativas, com peso igual ao número de proposições assinadas em
comum e um corte de outliers (percentil 99 de autores/proposição)
calculado uma única vez sobre toda a base 2003-2025.

Referência: Seção 4.2.6 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os arquivos
votacoesVotos-{ano}.xlsx / votacoesOrientacoes-{ano}.xlsx /
proposicoesAutores-{ano}.xlsx em PASTA (ver README.txt). Também requer
pandas e openpyxl, usados apenas por este script.
"""

import os, math, random, statistics, zipfile, urllib.request
from collections import defaultdict
from itertools import combinations
import pandas as pd
import networkx as nx

from assortatividade import calcular_r

PASTA        = './dados/camara'
URL_RELEASE  = 'https://github.com/Tluan07/Assortatividade_multi-categoria/releases/download/v1.0/dados_camara.zip'
N_AMOSTRAS   = 10_000
SEMENTE      = 42

def baixar_e_extrair_dados(pasta=PASTA, url=URL_RELEASE):
    os.makedirs(pasta, exist_ok=True)
    caminho_zip = os.path.join(pasta, 'dados_camara.zip')
    
    ja_baixado = any(nome.startswith('votacoesVotos') for nome in os.listdir(pasta)) if os.path.exists(pasta) else False
    
    if not ja_baixado:
        print(f"Baixando dados da Câmara de {url} ...")
        urllib.request.urlretrieve(url, caminho_zip)
        print("Extraindo arquivos ZIP...")
        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(pasta)
        if os.path.exists(caminho_zip):
            os.remove(caminho_zip)
        print("Dados da Câmara prontos em:", pasta)

baixar_e_extrair_dados()

# Blocos de mandato. 2016 fica isolado por ser o ano de transição do
# impeachment — nem colado em 2015 (Dilma) nem em 2017-2018 (Temer).
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


# -- Alinhamento com o governo: P_f (favor) e P_c (contra) ------------------
def carregar_favor_contra(pasta, anos):
    """Concatena os anos do período e devolve {deputado_id: proporção}
    de votos a favor/contra a orientação do governo, sobre o total de
    votações válidas do período inteiro (recontagem agregada, não média
    de percentuais anuais — evita distorcer anos com poucas votações)."""
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


# -- Pertinências fuzzy: trapézio relativo ao mandato + AND de Zadeh --------
def calcular_limiares(pct_favor, pct_contra):
    """p50/p75 de P_f e P_c, calculados sobre os deputados DESSE
    mandato — 'ser Governo' é relativo ao Congresso daquele período,
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


def s_fuzzy(mu_i, mu_j):
    """Simétrica por construção — não precisa da média (func(i,j)+func(j,i))/2
    usada para similaridades assimétricas como s_dir."""
    return max(mu_i[c] * mu_j[c] for c in ('Governo', 'Oposição', 'Centrão'))


# -- Rede de coautoria de proposições, com corte global de outliers ---------
def calcular_max_autores_global(pasta, todos_os_anos):
    """Corte de outliers (percentil 99 de autores/proposição) calculado
    uma única vez sobre toda a base 2003-2025 — não por mandato — para
    que o critério de 'proposição normal' não mude de tamanho a cada
    período e as redes continuem estruturalmente comparáveis entre si
    (ex.: PECs, que exigem assinatura de 1/3 da Câmara, aparecem em
    todos os mandatos, mas só distorcem a densidade se o corte for
    relativo)."""
    partes = [pd.read_excel(f) for ano in todos_os_anos
              if os.path.exists(f := os.path.join(pasta, f'proposicoesAutores-{ano}.xlsx'))]
    if not partes:
        raise FileNotFoundError(
            f"Nenhum arquivo 'proposicoesAutores-{{ano}}.xlsx' encontrado em '{os.path.abspath(pasta)}' "
            f"para os anos {todos_os_anos[0]}-{todos_os_anos[-1]}. Confira o valor de PASTA no topo do "
            f"script e se os arquivos foram salvos exatamente com esse nome."
        )
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


# -- S_obs, S_esp, dp, r, IC --------------------------------------------------
def calcular_s_obs(G, attrs, func):
    total_sim = total_peso = 0.0
    for u, v, d in G.edges(data=True):
        if u not in attrs or v not in attrs: continue
        w = d.get('peso', 1)
        total_sim += w * func(attrs[u], attrs[v])
        total_peso += w
    return total_sim / total_peso if total_peso else 0.0


def estimar_s_esp(G, attrs, func, n=N_AMOSTRAS):
    """Modelo nulo: sorteia pares proporcional à força (soma dos pesos do nó)."""
    random.seed(SEMENTE)
    nos    = [no for no in G.nodes() if no in attrs]
    forcas = [sum(d.get('peso', 1) for _, _, d in G.edges(no, data=True)) for no in nos]
    cats   = [attrs[no] for no in nos]
    amostras = []; tentativas = 0
    while len(amostras) < n and tentativas < n * 10:
        tentativas += 1
        i = random.choices(range(len(nos)), weights=forcas)[0]
        j = random.choices(range(len(nos)), weights=forcas)[0]
        if i != j:
            amostras.append(func(cats[i], cats[j]))
    if not amostras:
        return 0.0, 0.0
    return statistics.mean(amostras), statistics.stdev(amostras) if len(amostras) > 1 else 0.0


# -- Análise por mandato ------------------------------------------------------
def analisar_mandato(pasta, rotulo, anos, max_autores):
    pct_favor, pct_contra = carregar_favor_contra(pasta, anos)
    if not pct_favor:
        print(f"  [aviso] {rotulo}: sem votações válidas de governo — pulando")
        return None

    limiares = calcular_limiares(pct_favor, pct_contra)
    attrs_todos = {d: pertinencias_trapezoidais(pct_favor[d], pct_contra[d], limiares)
                   for d in pct_favor}

    G, attrs = construir_rede(pasta, anos, attrs_todos, max_autores)
    if G.number_of_edges() == 0:
        print(f"  [aviso] {rotulo}: rede sem arestas — pulando")
        return None

    S_obs = calcular_s_obs(G, attrs, s_fuzzy)
    S_esp, dp = estimar_s_esp(G, attrs, s_fuzzy)
    r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp, N_AMOSTRAS)

    print(f"\n{'='*78}")
    print(f"  Câmara dos Deputados — {rotulo}")
    print(f"{'='*78}")
    print(f"  Nós (deputados):  {G.number_of_nodes():,}   Arestas (coautoria):  {G.number_of_edges():,}")
    print(f"\n  {'Função':<12}{'S_obs':>8}{'S_esp':>8}{'dp':>9}{'r_desv':>9}{'IC_inf':>9}{'IC_sup':>9}")
    print(f"  {'-'*63}")
    print(f"  {'s_fuzzy':<12}{S_obs:>8.4f}{S_esp:>8.4f}{dp:>9.4f}{r:>9.4f}{ic_inf:>9.4f}{ic_sup:>9.4f}")

    return {'periodo': rotulo, 'n_nos': G.number_of_nodes(), 'n_arestas': G.number_of_edges(),
            'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp, 'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}


if __name__ == '__main__':
    todos_os_anos = sorted({a for anos in MANDATOS.values() for a in anos})
    max_autores_global = calcular_max_autores_global(PASTA, todos_os_anos)
    print(f"Corte global de outliers (p99 autores/proposição, 2003-2025): {max_autores_global:.0f}")

    resultados = {}
    for rotulo, anos in MANDATOS.items():
        try:
            resultados[rotulo] = analisar_mandato(PASTA, rotulo, anos, max_autores_global)
        except FileNotFoundError as e:
            print(f"[ERRO] {rotulo}: {e}")

    print(f"\n{'='*78}")
    print("  RESUMO — r_desvio [IC 95%], por mandato")
    print(f"{'='*78}")
    for rotulo, res in resultados.items():
        if res:
            print(f"  {rotulo:<28} r = {res['r_desvio']:>7.4f}  [{res['ic_inf']:.4f}, {res['ic_sup']:.4f}]")
