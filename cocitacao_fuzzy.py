# -*- coding: utf-8 -*-
"""
cocitacao_fuzzy.py

Aplicação à rede de citações da Web of Science. Leitura dos arquivos WoS,
construção do grafo dirigido, cálculo das pertinências fuzzy
(Curto/Médio/Longo, com base no número de páginas) e do índice r fuzzy.

Referência: Seção 4.2.3 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os dados brutos da WoS
em CAMINHO_BASE (ver README.txt).
"""

import os, re, math, random, statistics, zipfile, urllib.request, shutil
import networkx as nx

from assortatividade import calcular_r

CAMINHO_BASE = './dados'

URLS_DATASETS = {
    'hist_of_prob': 'url?id=3/releases/download/v1.0/dados_hist_of_prob.zip',
    'cryptography': 'https://github.com/Tluan07/Assortatividade_multi-categoria/releases/download/v1.0/dados_cryptography.zip'
}

def garantir_dados():
    for nome, url in URLS_DATASETS.items():
        pasta_destino = os.path.join(CAMINHO_BASE, nome)
        os.makedirs(pasta_destino, exist_ok=True)
        
        ja_baixado = len([f for f in os.listdir(pasta_destino) if not f.startswith('.')]) > 0
        if not ja_baixado:
            caminho_zip = os.path.join(pasta_destino, f'{nome}.zip')
            print(f"Baixando dataset '{nome}'...")
            urllib.request.urlretrieve(url, caminho_zip)
            print(f"Extraindo '{nome}'...")
            with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                zip_ref.extractall(pasta_destino)
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)
            for item in os.listdir(pasta_destino):
                subpasta = os.path.join(pasta_destino, item)
                if os.path.isdir(subpasta):
                    for f in os.listdir(subpasta):
                        shutil.move(os.path.join(subpasta, f), os.path.join(pasta_destino, f))
                    os.rmdir(subpasta)

garantir_dados()

TOPICOS = {
    'History of Probability' : os.path.join(CAMINHO_BASE, 'hist_of_prob'),
    'Cryptography'           : os.path.join(CAMINHO_BASE, 'cryptography'),
}
N_AMOSTRAS = 10_000
SEMENTE    = 42
RE_DOI     = re.compile(r'DOI\s+(\S+)', re.IGNORECASE)


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


def extrair_paginas(artigo):
    linhas = artigo.get('PG', [])
    try:
        return int(linhas[0].strip()) if linhas else None
    except ValueError:
        return None


def pertinencias(p):
    """Funções de pertinência trapezoidais com limites nos tercis (7, 9, 13, 15)."""
    curto = 1.0 if p <= 7 else max(0.0, (9 - p) / 2)
    medio = max(0.0, min((p - 7) / 2, 1.0, (15 - p) / 2)) if 7 < p < 15 else (1.0 if 9 <= p <= 13 else 0.0)
    longo = 0.0 if p <= 13 else min(1.0, (p - 13) / 2)
    return {'Curto': curto, 'Medio': medio, 'Longo': longo}


def s_fuzzy(mu_i, mu_j):
    """s_fuzzy = max{ μ_C(i)μ_C(j), μ_M(i)μ_M(j), μ_L(i)μ_L(j) }"""
    return max(
        mu_i['Curto'] * mu_j['Curto'],
        mu_i['Medio'] * mu_j['Medio'],
        mu_i['Longo'] * mu_j['Longo'],
    )


def construir_rede(artigos):
    doi_para_pag = {}
    for art in artigos:
        doi = extrair_doi(art); pag = extrair_paginas(art)
        if doi and pag and pag > 0:
            doi_para_pag[doi] = pag
    G = nx.DiGraph(); attrs = {}
    for doi, pag in doi_para_pag.items():
        G.add_node(doi); attrs[doi] = pertinencias(pag)
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
    if not artigos:
        print(f"  [ERRO] Nenhum artigo em {pasta}"); return None
    G, attrs = construir_rede(artigos)
    if not G.nodes():
        print("  [ERRO] Rede vazia."); return None

    pags = [extrair_paginas(a) for a in artigos if extrair_paginas(a)]
    n_cats = 3  # Curto, Médio, Longo

    print(f"\n{'═'*80}")
    print(f"  Citação Fuzzy — {nome}")
    print(f"{'═'*80}")
    print(f"  Nós:                   {G.number_of_nodes():,}")
    print(f"  Arestas:               {G.number_of_edges():,}")
    print(f"  Categorias distintas:  {n_cats}  (Curto / Médio / Longo)")
    print(f"  Páginas por artigo — min: {min(pags)}  max: {max(pags)}  média: {statistics.mean(pags):.1f}")

    print(f"\n  {'Função':<12} {'S_obs':>7} {'S_esp':>7} {'dp':>8} {'r_desv':>8} {'IC_inf':>8} {'IC_sup':>8}")
    print(f"  {'─'*70}")
    res = {}
    S_obs = calcular_s_obs(G, attrs, s_fuzzy)
    S_esp, dp = estimar_s_esp(G, attrs, s_fuzzy)
    r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp, N_AMOSTRAS)
    print(f"  {'s_fuzzy':<12} {S_obs:>7.4f} {S_esp:>7.4f} {dp:>8.4f} {r:>8.4f} {ic_inf:>8.4f} {ic_sup:>8.4f}")
    res['s_fuzzy'] = {'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp, 'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}
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
    for t in topicos:
        r = todos[t].get('s_fuzzy', {})
        if r:
            print(f"  {t:<30} r = {r['r_desvio']:.4f}  [{r['ic_inf']:.4f}, {r['ic_sup']:.4f}]")
