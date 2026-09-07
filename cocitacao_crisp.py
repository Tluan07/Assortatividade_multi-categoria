# -*- coding: utf-8 -*-
"""
cocitacao_crisp.py

Aplicação à rede de cocitação da Web of Science — versão crisp: cada
artigo é categorizado pelas áreas de pesquisa (WC) às quais pertence,
sem pertinência fuzzy.

Ver também: cocitacao_fuzzy.py (mesma base de dados, mas com categorias
fuzzy Curto/Médio/Longo baseadas no número de páginas).

Referência: Seção 4.2.3 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os dados brutos da WoS
em CAMINHO_BASE (ver README.txt).
"""

import os, re, math, random, statistics
import networkx as nx

from assortatividade import s_min, s_max, s_jaccard, s_dir, calcular_r

CAMINHO_BASE = './dados/wos'
TOPICOS = {
    'History of Probability': os.path.join(CAMINHO_BASE, 'hist_of_prob'),
    'Cryptography':           os.path.join(CAMINHO_BASE, 'cryptography'),
}
N_AMOSTRAS = 10_000
SEMENTE    = 42
RE_DOI     = re.compile(r'DOI\s+(\S+)', re.IGNORECASE)

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


def normalizar_doi(doi):
    return doi.strip().rstrip('.,;)').lower()


def extrair_doi(artigo):
    linhas = artigo.get('DI', [])
    return normalizar_doi(linhas[0]) if linhas else None


def extrair_areas(artigo):
    areas = set()
    for linha in artigo.get('WC', []):
        for area in linha.split(';'):
            area = area.strip().lower()
            if area: areas.add(area)
    return frozenset(areas)


def construir_rede(artigos):
    doi_para_areas = {}
    for art in artigos:
        doi = extrair_doi(art); areas = extrair_areas(art)
        if doi and areas:
            doi_para_areas[doi] = areas
    G = nx.DiGraph(); attrs = {}
    for doi, areas in doi_para_areas.items():
        G.add_node(doi); attrs[doi] = areas
    for art in artigos:
        doi_citante = extrair_doi(art)
        if doi_citante not in G:
            continue
        for linha in art.get('CR', []):
            m = RE_DOI.search(linha)
            if m:
                doi_citado = normalizar_doi(m.group(1))
                if doi_citado != doi_citante and doi_citado in G:
                    G.add_edge(doi_citante, doi_citado)
    isolados = list(nx.isolates(G))
    G.remove_nodes_from(isolados)
    attrs = {n: attrs[n] for n in G.nodes() if n in attrs}
    return G, attrs


def calcular_s_obs(G, attrs, func):
    sims = [(func(attrs[u], attrs[v]) + func(attrs[v], attrs[u])) / 2
            for u, v in G.edges() if u in attrs and v in attrs]
    return statistics.mean(sims) if sims else 0.0


def estimar_s_esp(G, attrs, func, n=N_AMOSTRAS):
    """Modelo nulo direcionado: citante ~ grau de saída, citado ~ grau de entrada."""
    random.seed(SEMENTE)
    nos       = [no for no in G.nodes() if no in attrs]
    g_saida   = [G.out_degree(no) for no in nos]
    g_entrada = [G.in_degree(no) for no in nos]
    cats = [attrs[no] for no in nos]
    amostras = []; tentativas = 0
    while len(amostras) < n and tentativas < n * 10:
        tentativas += 1
        i = random.choices(range(len(nos)), weights=g_saida)[0]
        j = random.choices(range(len(nos)), weights=g_entrada)[0]
        if i != j:
            amostras.append((func(cats[i], cats[j]) + func(cats[j], cats[i])) / 2)
    if not amostras:
        return 0.0, 0.0
    return statistics.mean(amostras), statistics.stdev(amostras) if len(amostras) > 1 else 0.0


def analisar_topico(nome, pasta):
    artigos = ler_pasta(pasta)
    if not artigos: print(f"  [ERRO] Nenhum artigo em {pasta}"); return None
    G, attrs = construir_rede(artigos)
    if not G.nodes(): print("  [ERRO] Rede vazia."); return None
    tamanhos = [len(attrs[n]) for n in G.nodes()]
    n_cats   = len({c for n in G.nodes() for c in attrs[n]})

    print(f"\n{'═'*80}")
    print(f"  Cocitação Crisp — {nome}")
    print(f"{'═'*80}")
    print(f"  Nós:                   {G.number_of_nodes():,}")
    print(f"  Arestas:               {G.number_of_edges():,}")
    print(f"  Categorias distintas:  {n_cats}")
    print(f"  Categorias por nó — min: {min(tamanhos)}  max: {max(tamanhos)}  média: {statistics.mean(tamanhos):.2f}")

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
    print("  RESUMO — r_desvio  [IC 95%]")
    print(f"{'═'*80}")
    print(f"  {'Função':<12}", end="")
    for t in topicos: print(f" {t[:20]:>24}", end="")
    print()
    print(f"  {'─'*70}")
    for nome_f, _ in SIM_FUNCS:
        print(f"  {nome_f:<12}", end="")
        for t in topicos:
            r = todos[t].get(nome_f, {})
            if r:
                print(f"  {r['r_desvio']:>7.4f} [{r['ic_inf']:.4f},{r['ic_sup']:.4f}]", end="")
        print()
