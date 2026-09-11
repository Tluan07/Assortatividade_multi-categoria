# -*- coding: utf-8 -*-
"""
coautoria_crisp_sem_peso.py

Aplicação às redes de coautoria da UFC e ITBA — versão SEM peso (crisp):
toda colaboração entra com peso 1, independentemente de quando ocorreu.
Leitura de dados WoS, construção do grafo de coautorias, extração de
áreas de pesquisa e cálculo dos índices sem peso.

Ver também: coautoria_crisp_com_peso.py (mesma base de dados, mas com
peso pelo tercil de recência da colaboração).

Referência: Seção 4.2.5 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os dados brutos da WoS
em CAMINHO_BASE (ver README.txt).
"""

import os, math, random, statistics
from itertools import combinations
from collections import defaultdict
import networkx as nx

from assortatividade import s_min, s_max, s_jaccard, s_dir, calcular_r

CAMINHO_BASE = '/content/sample_data/'
TOPICOS = {
    'History of Probability': os.path.join(CAMINHO_BASE, 'hist_of_prob'),
    'Cryptography':           os.path.join(CAMINHO_BASE, 'cryptography'),
}
N_AMOSTRAS  = 10_000
SEMENTE     = 42
MAX_AUTORES = 25  # limite fixado para evitar distorções por hiperautoria

SIM_FUNCS = [('s_min', s_min), ('s_max', s_max), ('s_Jaccard', s_jaccard), ('s_dir', s_dir)]


def ler_arquivo_wos(caminho):
    artigos = []; atual = {}; tag_atual = None
    with open(caminho, encoding='utf-8-sig', errors='replace') as f:
        for linha in f:
            linha = linha.rstrip('\n')
            if linha.startswith('ER'):
                if atual: artigos.append(atual)
                atual = {}; tag_atual = None; continue
            if linha.startswith('EF'): break
            tag = linha[:2].strip(); conteudo = linha[3:].strip()
            if tag:
                tag_atual = tag
                if tag not in atual: atual[tag] = []
                if conteudo: atual[tag].append(conteudo)
            elif tag_atual and conteudo:
                atual[tag_atual].append(conteudo)
    return artigos


def ler_pasta(pasta):
    todos = []
    for nome in sorted(f for f in os.listdir(pasta) if f.endswith('.txt')):
        todos.extend(ler_arquivo_wos(os.path.join(pasta, nome)))
    vistos = set(); unicos = []
    for a in todos:
        ut = a.get('UT', [None])[0]
        if ut and ut not in vistos: vistos.add(ut); unicos.append(a)
        elif not ut: unicos.append(a)
    return unicos


def extrair_areas(artigo):
    areas = set()
    for linha in artigo.get('WC', []):
        for area in linha.split(';'):
            area = area.strip().lower()
            if area: areas.add(area)
    return frozenset(areas)


def construir_rede(artigos, max_autores=MAX_AUTORES):
    G = nx.Graph(); areas_por_autor = defaultdict(set)
    n_validos = n_excluidos = 0

    for artigo in artigos:
        autores = list({a.strip().lower() for linha in artigo.get('AU', []) for a in linha.split('\n') if a.strip()})
        areas = extrair_areas(artigo)
        if not autores or not areas:
            continue

        n_validos += 1
        if len(autores) > max_autores:
            n_excluidos += 1
            continue

        for autor in autores:
            areas_por_autor[autor].update(areas)
        for a1, a2 in combinations(sorted(set(autores)), 2):
            if not G.has_edge(a1, a2):
                G.add_edge(a1, a2)
            for a in (a1, a2):
                if not G.has_node(a):
                    G.add_node(a)

    attrs = {a: frozenset(ar) for a, ar in areas_por_autor.items()}
    G.remove_nodes_from([n for n in G.nodes() if not attrs.get(n)])
    G.remove_nodes_from(list(nx.isolates(G)))

    info_rede = {'validos': n_validos, 'excluidos': n_excluidos}
    return G, {n: attrs[n] for n in G.nodes() if n in attrs}, info_rede


def calcular_s_obs(G, attrs, func):
    sims = [(func(attrs[u], attrs[v]) + func(attrs[v], attrs[u])) / 2
            for u, v in G.edges() if u in attrs and v in attrs]
    return statistics.mean(sims) if sims else 0.0


def estimar_s_esp(G, attrs, func, n=N_AMOSTRAS):
    """Modelo nulo: sorteia pares proporcional ao grau."""
    random.seed(SEMENTE)
    nos = [no for no in G.nodes() if no in attrs]
    graus = [G.degree(no) for no in nos]
    cats = [attrs[no] for no in nos]
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


def analisar_topico(nome, pasta):
    artigos = ler_pasta(pasta)
    if not artigos:
        print(f"  [ERRO] Nenhum artigo em {pasta}"); return None

    G, attrs, info = construir_rede(artigos)
    tamanhos = [len(attrs[n]) for n in G.nodes()]
    n_cats = len({c for n in G.nodes() for c in attrs[n]})

    print(f"\n{'═'*80}")
    print(f"  Coautoria Crisp (sem peso) — {nome}")
    print(f"{'═'*80}")
    print(f"  Artigos analisados com autores:  {info['validos']:,}")
    print(f"  Artigos excluídos (>{MAX_AUTORES} aut.):   {info['excluidos']:,}")
    print(f"  Nós (Autores válidos):           {G.number_of_nodes():,}")
    print(f"  Arestas (Colaborações):          {G.number_of_edges():,}")
    print(f"  Categorias distintas:            {n_cats}")
    print(f"  Categorias por nó — min: {min(tamanhos)} max: {max(tamanhos)} média: {statistics.mean(tamanhos):.2f}")
    print(f"\n  {'Função':<12} {'S_obs':>7} {'S_esp':>7} {'dp':>8} {'r_desv':>8} {'IC_inf':>8} {'IC_sup':>8}")
    print(f"  {'─'*70}")

    res = {}
    for nome_f, func in SIM_FUNCS:
        S_obs = calcular_s_obs(G, attrs, func)
        S_esp, dp_mc = estimar_s_esp(G, attrs, func)
        dp = math.sqrt(S_esp * (1 - S_esp)) if nome_f in ('s_min', 's_max') else dp_mc
        r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp, N_AMOSTRAS)
        print(f"  {nome_f:<12} {S_obs:>7.4f} {S_esp:>7.4f} {dp:>8.4f} {r:>8.4f} {ic_inf:>8.4f} {ic_sup:>8.4f}")
        res[nome_f] = {'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp, 'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}
    return res


if __name__ == '__main__':
    todos = {}
    for nome, pasta in TOPICOS.items():
        try:
            todos[nome] = analisar_topico(nome, pasta)
        except FileNotFoundError as e:
            print(f"\n[ERRO] {e}")

    topicos = [t for t in todos if todos[t]]
    print(f"\n{'═'*80}")
    print("  RESUMO — r_desvio [IC 95%] (Rede Não Ponderada Sem Hiperautoria)")
    print(f"{'═'*80}")
    print(f"  {'Função':<12}", end="")
    for t in topicos:
        print(f" {t[:20]:>24}", end="")
    print()
    print(f"  {'─'*70}")
    for nome_f, _ in SIM_FUNCS:
        print(f"  {nome_f:<12}", end="")
        for t in topicos:
            r = todos[t].get(nome_f, {})
            if r:
                print(f" {r['r_desvio']:>7.4f} [{r['ic_inf']:.4f},{r['ic_sup']:.4f}]", end="")
        print()
