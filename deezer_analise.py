# -*- coding: utf-8 -*-
"""
deezer_analise.py

Aplicação às redes sociais do Deezer (RO, HR, HU). Três níveis de
granularidade de gêneros musicais, estimação de S_esp por Monte Carlo
(N = 10.000 amostras) e intervalos de confiança de 95%.

Referência: Seção 4.2.4 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os arquivos
<PAIS>_edges.csv / <PAIS>_genres.json em DATA_DIR (ver README.txt).
"""

import os, json, csv, math, random, statistics
import networkx as nx

from assortatividade import s_min, s_max, s_jaccard, s_dir, calcular_r

DATA_DIR   = './dados/deezer'
PAISES     = ['RO', 'HR', 'HU']
N_AMOSTRAS = 10_000
SEMENTE    = 42

SIM_FUNCS = [('s_min', s_min), ('s_max', s_max), ('s_Jaccard', s_jaccard), ('s_dir', s_dir)]


def construir_rede(pais, pasta):
    arestas = []
    with open(os.path.join(pasta, f"{pais}_edges.csv")) as f:
        reader = csv.reader(f); next(reader)
        for linha in reader:
            if len(linha) >= 2:
                arestas.append((linha[0].strip(), linha[1].strip()))
    with open(os.path.join(pasta, f"{pais}_genres.json")) as f:
        generos = {str(k): frozenset(v) for k, v in json.load(f).items()}
    G = nx.Graph()
    for u, v in arestas:
        G.add_edge(u, v)
    attrs = {n: generos[str(n)] for n in G.nodes() if str(n) in generos and generos[str(n)]}
    G.remove_nodes_from([n for n in G.nodes() if n not in attrs])
    return G, attrs


def calcular_s_obs(G, attrs, func):
    sims = [(func(attrs[u], attrs[v]) + func(attrs[v], attrs[u])) / 2
            for u, v in G.edges() if u in attrs and v in attrs]
    return statistics.mean(sims) if sims else 0.0


def estimar_s_esp(G, attrs, func, n=N_AMOSTRAS):
    """Modelo nulo: sorteia pares proporcional ao grau."""
    random.seed(SEMENTE)
    nos   = [no for no in G.nodes() if no in attrs]
    graus = [G.degree(no) for no in nos]
    cats  = [attrs[no] for no in nos]
    amostras = []; tentativas = 0
    while len(amostras) < n and tentativas < n * 10:
        tentativas += 1
        i = random.choices(range(len(nos)), weights=graus)[0]
        j = random.choices(range(len(nos)), weights=graus)[0]
        if i != j:
            amostras.append((func(cats[i], cats[j]) + func(cats[j], cats[i])) / 2)
    if not amostras:
        return 0.0, 0.0
    return statistics.mean(amostras), statistics.stdev(amostras) if len(amostras) > 1 else 0.0


def analisar_pais(pais):
    G, attrs = construir_rede(pais, DATA_DIR)
    tamanhos = [len(attrs[n]) for n in G.nodes()]
    n_cats   = len({c for n in G.nodes() for c in attrs[n]})

    print(f"\n{'═'*80}")
    print(f"  Deezer — {pais}")
    print(f"{'═'*80}")
    print(f"  Nós:                   {G.number_of_nodes():,}")
    print(f"  Arestas:               {G.number_of_edges():,}")
    print(f"  Categorias distintas:  {n_cats}")
    print(f"  Categorias por nó — min: {min(tamanhos)}  max: {max(tamanhos)}  média: {statistics.mean(tamanhos):.2f}")

    print(f"\n  {'Função':<12} {'S_obs':>7} {'S_esp':>7} {'dp':>8} {'r_desv':>8} {'IC_inf':>8} {'IC_sup':>8}")
    print(f"  {'─'*70}")
    res = {}
    for nome, func in SIM_FUNCS:
        S_obs = calcular_s_obs(G, attrs, func)
        S_esp, dp_mc = estimar_s_esp(G, attrs, func)
        dp = math.sqrt(S_esp * (1 - S_esp)) if nome in ('s_min', 's_max') else dp_mc
        r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp, N_AMOSTRAS)
        print(f"  {nome:<12} {S_obs:>7.4f} {S_esp:>7.4f} {dp:>8.4f} {r:>8.4f} {ic_inf:>8.4f} {ic_sup:>8.4f}")
        res[nome] = {'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp, 'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}
    return res


if __name__ == '__main__':
    todos = {}
    for pais in PAISES:
        try:
            todos[pais] = analisar_pais(pais)
        except FileNotFoundError as e:
            print(f"\n[ERRO] {e}")

    print(f"\n{'═'*80}")
    print("  RESUMO — r_desvio  [IC 95%]")
    print(f"{'═'*80}")
    print(f"  {'Função':<12}", end="")
    for pais in PAISES:
        print(f" {pais:>24}", end="")
    print()
    print(f"  {'─'*80}")
    for nome, _ in SIM_FUNCS:
        print(f"  {nome:<12}", end="")
        for pais in PAISES:
            r = todos.get(pais, {}).get(nome, {})
            if r:
                print(f"  {r['r_desvio']:>7.4f} [{r['ic_inf']:.4f},{r['ic_sup']:.4f}]", end="")
            else:
                print(f"  {'N/A':>24}", end="")
        print()
