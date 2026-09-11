# -*- coding: utf-8 -*-
"""
coautoria_ufc_itba.py

Aplicação às redes de coautoria da UFC e ITBA. Leitura de dados WoS,
construção do grafo ponderado de coautorias (peso = tercil de recência
da colaboração: 1 = mais antigo, 3 = mais recente), extração de áreas
de pesquisa e cálculo dos índices com peso.

Referência: Seção 4.2.5 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os dados brutos da WoS
em CAMINHO_BASE (ver README.txt).
"""

import os, math, random, statistics
from collections import defaultdict
from itertools import combinations
import networkx as nx

from assortatividade import calcular_r

CAMINHO_BASE = '/content/sample_data/'
TOPICOS = {
    'History of Probability': os.path.join(CAMINHO_BASE, 'hist_of_prob'),
    'Cryptography':           os.path.join(CAMINHO_BASE, 'cryptography'),
}
N_AMOSTRAS  = 10_000
SEMENTE     = 42
MAX_AUTORES = 25  # exclui artigos hiperautorados (percentil 99 em History of Probability;
                   # acima do p99 em Cryptography), mesmo limite fixo nos dois tópicos


# -- Leitura dos dados -----------------------------------------------------
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
                atual.setdefault(tag, [])
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


def autores(a):
    vistos = set(); out = []
    for linha in a.get('AU', []):
        for nome in linha.split('\n'):
            nome = nome.strip().lower()
            if nome and nome not in vistos: vistos.add(nome); out.append(nome)
    return out


def areas(a):
    return frozenset(c.strip().lower() for l in a.get('WC', []) for c in l.split(';') if c.strip())


def ano(a):
    py = a.get('PY', [])
    try: return int(py[0].strip()) if py else None
    except ValueError: return None


def tercis(valores):
    v = sorted(valores); n = len(v)
    if n < 3: return (v[0] if v else 0), (v[-1] if v else 0)
    return v[n // 3], v[2 * n // 3]


# -- Construção do grafo base (SEM exigir ano) ------------------------------
def construir_rede_base(artigos, max_autores=MAX_AUTORES):
    """
    Constrói o grafo de coautoria completo — toda aresta válida entra,
    independentemente de o artigo ter ano (PY) preenchido ou não — e
    registra, à parte, o ano de colaboração mais recente conhecido para
    cada par (quando existir). O ano nunca decide se uma aresta existe;
    ele só é usado depois, em aplicar_peso_tercil, para calcular o peso
    de recência.
    """
    G = nx.Graph()
    cats_por_autor = defaultdict(set)
    ano_par = {}
    n_validos = n_excluidos = 0

    for a in artigos:
        aut, cat, ano_a = autores(a), areas(a), ano(a)
        if not aut or not cat:
            continue
        n_validos += 1
        if len(aut) > max_autores:
            n_excluidos += 1
            continue
        for x in aut:
            cats_por_autor[x].update(cat)
            G.add_node(x)
        if len(aut) < 2:
            continue
        for x, y in combinations(sorted(set(aut)), 2):
            chave = (x, y) if x < y else (y, x)
            G.add_edge(x, y)
            if ano_a:
                ano_par[chave] = max(ano_par.get(chave, 0), ano_a)

    attrs = {a: frozenset(c) for a, c in cats_por_autor.items()}
    G.remove_nodes_from([n for n in G.nodes() if not attrs.get(n)])
    G.remove_nodes_from(list(nx.isolates(G)))
    attrs = {n: attrs[n] for n in G.nodes() if n in attrs}
    info = {'artigos': n_validos, 'excluidos': n_excluidos,
            'nos': G.number_of_nodes(), 'arestas': G.number_of_edges()}
    return G, attrs, ano_par, info


# -- Aplicação do peso (tercil de recência) ---------------------------------
def aplicar_peso_tercil(G, ano_par):
    """
    Peso = tercil do ano de colaboração mais recente do par
    (1 = mais antigo, 3 = mais recente). Pares sem ano conhecido ficam
    de fora desta rede.
    """
    anos_conhecidos = list(ano_par.values())
    if not anos_conhecidos:
        return G.copy(), {}
    c1, c2 = tercis(anos_conhecidos)
    H = nx.Graph()
    H.add_nodes_from(G.nodes())
    for x, y in G.edges():
        chave = (x, y) if x < y else (y, x)
        a_par = ano_par.get(chave)
        if a_par is None:
            continue
        peso = 1 if a_par <= c1 else (2 if a_par <= c2 else 3)
        H.add_edge(x, y, peso=peso)
    H.remove_nodes_from(list(nx.isolates(H)))
    return H, {'c1': c1, 'c2': c2}


from assortatividade import s_min, s_max, s_jaccard, s_dir

SIM_FUNCS = [('s_min', s_min), ('s_max', s_max), ('s_Jaccard', s_jaccard), ('s_dir', s_dir)]


# -- S_obs, S_esp, dp, r, IC -------------------------------------------------
def calcular_s_obs(G, attrs, func):
    total_sim = total_peso = 0.0
    for u, v, d in G.edges(data=True):
        if u not in attrs or v not in attrs: continue
        w = d.get('peso', 1)
        total_sim += w * (func(attrs[u], attrs[v]) + func(attrs[v], attrs[u])) / 2
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
            amostras.append((func(cats[i], cats[j]) + func(cats[j], cats[i])) / 2)
    if not amostras:
        return 0.0, 0.0
    return statistics.mean(amostras), statistics.stdev(amostras) if len(amostras) > 1 else 0.0


# -- Impressão de tabela (S_obs, S_esp, dp, r, IC) ---------------------------
def imprimir_tabela(G, attrs, titulo):
    print(f"\n  {titulo}")
    print(f"  {'Função':<12}{'S_obs':>8}{'S_esp':>8}{'dp':>9}{'r_desv':>9}{'IC_inf':>9}{'IC_sup':>9}")
    print(f"  {'-'*63}")
    resultado = {}
    for nome_f, func in SIM_FUNCS:
        S_obs = calcular_s_obs(G, attrs, func)
        S_esp, dp_mc = estimar_s_esp(G, attrs, func)
        dp = math.sqrt(S_esp * (1 - S_esp)) if nome_f in ('s_min', 's_max') else dp_mc
        r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp, N_AMOSTRAS)
        print(f"  {nome_f:<12}{S_obs:>8.4f}{S_esp:>8.4f}{dp:>9.4f}{r:>9.4f}{ic_inf:>9.4f}{ic_sup:>9.4f}")
        resultado[nome_f] = {'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp,
                              'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}
    return resultado


# -- Análise por tópico -------------------------------------------------------
def analisar_topico(nome, pasta):
    artigos = ler_pasta(pasta)
    if not artigos:
        print(f"  [ERRO] Nenhum artigo em {pasta}")
        return None

    G_base, attrs, ano_par, info = construir_rede_base(artigos)
    G_ter, meta_ter = aplicar_peso_tercil(G_base, ano_par)

    print(f"\n{'='*78}")
    print(f"  Coautoria - {nome}")
    print(f"{'='*78}")
    print(f"  Artigos considerados:            {info['artigos']:,}")
    print(f"  Excluídos (>{MAX_AUTORES} autores):        {info['excluidos']:,}")
    print(f"  Nós:  {info['nos']:,}   Arestas (rede completa): {info['arestas']:,}")
    if meta_ter:
        pares_sem_ano = G_base.number_of_edges() - G_ter.number_of_edges()
        print(f"  Cortes de tercil de recência — T1 <= {meta_ter['c1']}  |  "
              f"T1 < T2 <= {meta_ter['c2']}  |  T3 > {meta_ter['c2']}")
        print(f"  Arestas na rede ponderada (com ano conhecido): {G_ter.number_of_edges():,}"
              f"   ({pares_sem_ano:,} pares sem ano ficaram de fora dessa rede)")

    return imprimir_tabela(G_ter, attrs, "Com peso (tercil de recência da colaboração)")


if __name__ == '__main__':
    todos = {}
    for nome, pasta in TOPICOS.items():
        try:
            todos[nome] = analisar_topico(nome, pasta)
        except FileNotFoundError as e:
            print(f"[ERRO] {nome}: {e}")

    print(f"\n{'='*78}")
    print("  RESUMO — r_desv (peso por tercil de recência)")
    print(f"{'='*78}")
    for nome, res in todos.items():
        if not res: continue
        print(f"\n  {nome}")
        print(f"  {'Função':<12}{'r_desvio':>10}")
        for f, _ in SIM_FUNCS:
            print(f"  {f:<12}{res[f]['r_desvio']:>10.4f}")
