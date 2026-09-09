# -*- coding: utf-8 -*-
"""
Câmara dos Deputados — Assortatividade Multi-Categoria Fuzzy por Mandato
==========================================================================

Para cada mandato (rede de coautoria de proposições daquele período):
  1) calcula P_f (pct_favor) e P_c (pct_contra) de cada deputado a partir
     das orientações de voto do governo;
  2) calcula os limiares trapezoidais (p50 e p75 de P_f e de P_c) *dentro
     daquele mandato* — ou seja, "ser Governo" é sempre relativo ao
     Congresso daquele período, não a uma régua fixa global;
  3) converte (P_f, P_c) em graus de pertinência fuzzy a Governo, Oposição
     e Centrão via trapezoidal + min (ver seção 3);
  4) constrói a rede de coautoria de proposições do mandato, usando um
     corte de outliers (proposições com nº atípico de coautores, ex.:
     PECs, que exigem assinatura de 1/3 da Câmara) calculado UMA ÚNICA
     VEZ sobre a base inteira 2003-2025 — diferente dos limiares
     políticos do passo 2, essa é uma regra de limpeza de dado e precisa
     ser a mesma em todos os mandatos, senão as redes deixam de ser
     estruturalmente comparáveis entre si (ver seção 1.5);
  5) calcula S_obs, S_esp (Monte Carlo) e o índice r_dp com s_fuzzy;
  6) roda um teste de permutação vetorizado (numpy) — embaralha os
     vetores de pertinência entre os nós, mantendo a rede fixa — para
     obter um p-valor: a fração de rótulos embaralhados que produz uma
     diferença S_obs-S_esp tão extrema quanto a real. H0 = "a categoria
     não tem relação com a estrutura da rede". Com 0 sucessos em N
     tentativas, reporta p < 3/N (regra dos três), não "p=0";
  7) consolida tudo em duas tabelas enxutas e um gráfico comparando os
     mandatos (a tabela completa, com diagnóstico de densidade, vai só
     para o CSV, para não poluir a saída no console).

Nenhuma função é redefinida ao longo do arquivo — cada uma existe uma
única vez, e o estado (limiares, atributos) sempre passa explícito por
parâmetro, nunca por variável global reaproveitada.
"""

import os
import random
import statistics
import math
import warnings
from collections import defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ══════════════════════════════════════════════════════════════════════
# 0. Configuração
# ══════════════════════════════════════════════════════════════════════

PASTA = '/content/sample_data/camara_deputados'
N_AMOSTRAS = 10_000
N_PERMUTACOES = 10_000  # viável em segundos com a versão vetorizada (numpy)
ALPHA = 0.05          # nível de significância para o teste
SEMENTE = 42

# Mesmos blocos já validados no diagnóstico de votações (Parte 1/2 do
# script anterior). 2016 fica isolado por ser o ano de transição do
# impeachment — nem colado em 2015 nem em 2017-2018.
MANDATOS = {
    '2003-2006': [2003, 2004, 2005, 2006],
    '2007-2010': [2007, 2008, 2009, 2010],
    '2011-2014': [2011, 2012, 2013, 2014],
    '2015 (Dilma)': [2015],
    '2016 (transição)': [2016],
    '2017-2018 (Temer)': [2017, 2018],
    '2019-2022': [2019, 2020, 2021, 2022],
    '2023-2025 (atual, parcial)': [2023, 2024, 2025],
}


# ══════════════════════════════════════════════════════════════════════
# 1. Carregamento de votos → P_f (pct_favor) e P_c (pct_contra)
# ══════════════════════════════════════════════════════════════════════

def carregar_favor_contra(pasta, anos):
    """Concatena os anos do período e devolve dois dicts
    {deputado_id: proporção}, calculados sobre o total de votações
    válidas do período inteiro (não é média de proporções anuais)."""
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
    base = pd.MultiIndex.from_product([deputados, gov.idVotacao], names=['deputado_id', 'idVotacao']).to_frame(index=False)
    base = base.merge(gov, on='idVotacao', how='left')
    base = base.merge(votos[['idVotacao', 'deputado_id', 'voto']], on=['idVotacao', 'deputado_id'], how='left')

    base['favor'] = (base.voto.isin(['Sim', 'Não'])) & (base.voto == base.orientacao_governo)
    base['contra'] = (base.voto.isin(['Sim', 'Não'])) & (base.voto != base.orientacao_governo)

    r = base.groupby('deputado_id').agg(favor=('favor', 'sum'), contra=('contra', 'sum'))
    pct_favor = (r.favor / total_votacoes).to_dict()
    pct_contra = (r.contra / total_votacoes).to_dict()
    return pct_favor, pct_contra


# ══════════════════════════════════════════════════════════════════════
# 2. Limiares trapezoidais (p50/p75), recalculados a cada mandato
# ══════════════════════════════════════════════════════════════════════

def calcular_limiares(pct_favor, pct_contra):
    """p50 e p75 de P_f e P_c, calculados sobre os deputados DESSE
    mandato. É essa recalibração que faz 'Governo' significar 'quartil
    de cima daquele Congresso específico', não um valor absoluto."""
    fav = pd.Series(pct_favor)
    con = pd.Series(pct_contra)
    return {
        'favor_p50': fav.quantile(0.50),
        'favor_p75': fav.quantile(0.75),
        'contra_p50': con.quantile(0.50),
        'contra_p75': con.quantile(0.75),
    }


# ══════════════════════════════════════════════════════════════════════
# 3. Pertinências fuzzy: trapézio em cada eixo + mínimo dos complementos
# ══════════════════════════════════════════════════════════════════════

def _trapezio(valor, limiar_inf, limiar_sup):
    """Sobe linearmente de 0 (em limiar_inf) a 1 (em limiar_sup)."""
    if limiar_sup <= limiar_inf:
        return 1.0 if valor >= limiar_sup else 0.0
    if valor <= limiar_inf:
        return 0.0
    if valor >= limiar_sup:
        return 1.0
    return (valor - limiar_inf) / (limiar_sup - limiar_inf)


def pertinencias_trapezoidais(pct_favor, pct_contra, limiares):
    """x = mu_Governo (trapézio em P_f); z = mu_Oposição (trapézio em
    P_c); y = mu_Centrão = min(1-x, 1-z) — ver validação feita
    anteriormente com o professor (fuzzy AND de Zadeh)."""
    x = _trapezio(pct_favor, limiares['favor_p50'], limiares['favor_p75'])
    z = _trapezio(pct_contra, limiares['contra_p50'], limiares['contra_p75'])
    y = min(1 - x, 1 - z)
    return {'Governo': x, 'Oposição': z, 'Centrão': y}


# ══════════════════════════════════════════════════════════════════════
# 4. Similaridade fuzzy entre dois deputados
# ══════════════════════════════════════════════════════════════════════

def s_fuzzy(a, b):
    return max(a['Governo'] * b['Governo'],
               a['Oposição'] * b['Oposição'],
               a['Centrão'] * b['Centrão'])


# ══════════════════════════════════════════════════════════════════════
# 5. Rede de coautoria — corte de outliers FIXO (global) + construção
# ══════════════════════════════════════════════════════════════════════

def calcular_max_autores_global(pasta, todos_os_anos):
    """Corte de outliers calculado UMA VEZ sobre a base inteira (todos os
    mandatos juntos), não por mandato. Isso evita que o próprio limiar de
    'proposição normal' mude de tamanho a cada período — o que quebraria
    a comparabilidade estrutural das redes (ex.: PECs, que exigem
    assinatura de 1/3 da Câmara — 171 de 513 —, aparecem em todos os
    mandatos, mas só distorcem a densidade se o corte for relativo)."""
    partes = []
    for ano in todos_os_anos:
        f = os.path.join(pasta, f'proposicoesAutores-{ano}.xlsx')
        if os.path.exists(f):
            partes.append(pd.read_excel(f))
    df = pd.concat(partes, ignore_index=True)
    dep = df[(df.codTipoAutor == 10000) & df.idDeputadoAutor.notna()].copy()
    dep['idDeputadoAutor'] = dep['idDeputadoAutor'].astype(int)
    por_prop = dep.groupby('idProposicao')['idDeputadoAutor'].apply(lambda s: sorted(set(s)))
    n_autores = por_prop.apply(len)
    max_autores_global = n_autores.quantile(0.99)
    print(f"Corte global de outliers (p99 de autores/proposição, 2003-2025): {max_autores_global:.0f}")
    return max_autores_global


def construir_rede(pasta, anos, attrs_todos, max_autores):
    """attrs_todos: dict {deputado_id: {'Governo':..,'Oposição':..,'Centrão':..}}
    já calculado antes de chamar esta função. max_autores: corte de
    outliers FIXO (calculado uma vez sobre toda a base, não por mandato
    — ver calcular_max_autores_global)."""
    partes = []
    for ano in anos:
        f = os.path.join(pasta, f'proposicoesAutores-{ano}.xlsx')
        if os.path.exists(f):
            partes.append(pd.read_excel(f))
    if not partes:
        return nx.Graph(), {}, {}
    df = pd.concat(partes, ignore_index=True)

    dep = df[(df.codTipoAutor == 10000) & df.idDeputadoAutor.notna()].copy()
    dep['idDeputadoAutor'] = dep['idDeputadoAutor'].astype(int)
    por_prop = dep.groupby('idProposicao')['idDeputadoAutor'].apply(lambda s: sorted(set(s)))

    n_autores = por_prop.apply(len)
    excluidos = int((n_autores > max_autores).sum())

    diagnostico = {
        'n_proposicoes': len(por_prop),
        'autores_por_prop_mediana': n_autores.median() if len(n_autores) else 0,
        'autores_por_prop_media': round(n_autores.mean(), 2) if len(n_autores) else 0,
        'autores_por_prop_p95': n_autores.quantile(0.95) if len(n_autores) else 0,
        'autores_por_prop_max': n_autores.max() if len(n_autores) else 0,
        'proposicoes_excluidas_corte_global': excluidos,
    }

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

    n = G.number_of_nodes()
    max_arestas = n * (n - 1) / 2
    diagnostico['densidade'] = round(G.number_of_edges() / max_arestas, 4) if max_arestas else 0.0

    return G, attrs, diagnostico


# ══════════════════════════════════════════════════════════════════════
# 6. S_obs, S_esp (Monte Carlo) e índice r_dp com IC 95%
# ══════════════════════════════════════════════════════════════════════

def calcular_s_obs(G, attrs, func):
    sim = peso = 0.0
    for u, v, d in G.edges(data=True):
        w = d.get('peso', 1)
        sim += w * func(attrs[u], attrs[v])
        peso += w
    return sim / peso if peso else 0.0


def estimar_s_esp(G, attrs, func, n=N_AMOSTRAS, semente=SEMENTE):
    random.seed(semente)
    nos = list(G.nodes())
    forcas = [sum(d.get('peso', 1) for _, _, d in G.edges(no, data=True)) for no in nos]
    cats = [attrs[no] for no in nos]
    amostras = []
    while len(amostras) < n:
        i = random.choices(range(len(nos)), weights=forcas)[0]
        j = random.choices(range(len(nos)), weights=forcas)[0]
        if i != j:
            amostras.append(func(cats[i], cats[j]))
    return statistics.mean(amostras), statistics.stdev(amostras)


def calcular_r(S_obs, S_esp, dp, n=N_AMOSTRAS):
    if dp <= 0:
        return 0.0, 0.0, 0.0
    r = (S_obs - S_esp) / dp
    m = 1.96 / math.sqrt(n)
    return r, r - m, r + m


def teste_permutacao(G, attrs, n_perm=N_PERMUTACOES, n_pares=2000, semente=SEMENTE):
    """H0: a categoria não tem relação com a rede. Embaralha os vetores de
    pertinência entre os nós (rede/pesos ficam fixos) e recalcula
    D=S_obs-S_esp a cada embaralhamento, usando a MESMA amostra fixa de
    pares para D_real e para cada D_pi. Vetorizado com numpy — cada
    embaralhamento é uma operação de matriz, não um laço em Python.
    p-valor = fração de |D_pi| >= |D_real|."""
    rng = np.random.default_rng(semente + 1)
    nos = list(G.nodes())
    idx = {no: i for i, no in enumerate(nos)}
    n = len(nos)

    CATS = ['Governo', 'Oposição', 'Centrão']
    matriz_attrs = np.array([[attrs[no][c] for c in CATS] for no in nos])

    arestas = list(G.edges(data=True))
    ei = np.array([idx[u] for u, v, d in arestas])
    ej = np.array([idx[v] for u, v, d in arestas])
    pesos = np.array([d.get('peso', 1) for u, v, d in arestas], dtype=float)
    total_W = pesos.sum()

    forcas = np.array([sum(d.get('peso', 1) for _, _, d in G.edges(no, data=True)) for no in nos])
    p_forcas = forcas / forcas.sum()
    pi = rng.choice(n, size=n_pares, p=p_forcas)
    pj = rng.choice(n, size=n_pares, p=p_forcas)
    validos = pi != pj
    pi, pj = pi[validos], pj[validos]

    def calcular_D(M):
        S_obs = np.sum(pesos * np.max(M[ei] * M[ej], axis=1)) / total_W
        S_esp = np.mean(np.max(M[pi] * M[pj], axis=1))
        return S_obs - S_esp

    D_real = calcular_D(matriz_attrs)

    contagem = 0
    M = matriz_attrs.copy()
    for _ in range(n_perm):
        ordem = rng.permutation(n)
        if abs(calcular_D(M[ordem])) >= abs(D_real):
            contagem += 1
    return contagem / n_perm


def formatar_p(p, n_perm=N_PERMUTACOES):
    """Regra dos três: com 0 sucessos em N tentativas, reporta p < 3/N
    (95% de confiança) em vez de 'p=0', que a amostra não sustenta."""
    return f"< {3/n_perm:.4f}" if p == 0 else f"{p:.4f}"


# ══════════════════════════════════════════════════════════════════════
# 7. Pipeline completo para um único mandato
# ══════════════════════════════════════════════════════════════════════

def analisar_mandato(pasta, rotulo, anos, max_autores):
    pct_favor, pct_contra = carregar_favor_contra(pasta, anos)
    if not pct_favor:
        print(f"  [aviso] {rotulo}: sem votações válidas de governo — pulando")
        return None

    limiares = calcular_limiares(pct_favor, pct_contra)
    attrs_todos = {d: pertinencias_trapezoidais(pct_favor[d], pct_contra[d], limiares)
                   for d in pct_favor}

    G, attrs, diag = construir_rede(pasta, anos, attrs_todos, max_autores)
    if G.number_of_edges() == 0:
        print(f"  [aviso] {rotulo}: rede sem arestas — pulando")
        return None

    S_obs = calcular_s_obs(G, attrs, s_fuzzy)
    S_esp, dp = estimar_s_esp(G, attrs, s_fuzzy)
    r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp)
    p_perm = teste_permutacao(G, attrs)

    dominantes = [max(mu, key=mu.get) for mu in attrs.values()]
    contagem = {c: dominantes.count(c) for c in ['Governo', 'Oposição', 'Centrão']}

    return {
        'periodo': rotulo,
        'n_nos_rede': G.number_of_nodes(),
        'n_arestas_rede': G.number_of_edges(),
        'densidade': diag['densidade'],
        'favor_p50': round(limiares['favor_p50'], 4),
        'favor_p75': round(limiares['favor_p75'], 4),
        'contra_p50': round(limiares['contra_p50'], 4),
        'contra_p75': round(limiares['contra_p75'], 4),
        'n_governo': contagem['Governo'],
        'n_oposicao': contagem['Oposição'],
        'n_centrao': contagem['Centrão'],
        'S_obs': round(S_obs, 4),
        'S_esp': round(S_esp, 4),
        'sqrt_V': round(dp, 4),
        'r_dp': round(r, 4),
        'IC_95': f"[{ic_inf:.4f}, {ic_sup:.4f}]",
        'p_perm': p_perm,
        'p_perm_fmt': formatar_p(p_perm),
        'significativo': 'sim' if p_perm < ALPHA or p_perm == 0 else 'não',
    }


# ══════════════════════════════════════════════════════════════════════
# 8. Execução: todos os mandatos + tabela consolidada + gráfico
# ══════════════════════════════════════════════════════════════════════

def plot_evolucao_r(df, caminho_saida):
    ic = df.IC_95.str.strip('[]').str.split(',', expand=True).astype(float)
    ic_inf, ic_sup = ic[0], ic[1]
    fig, ax = plt.subplots(figsize=(max(10, len(df) * 1.3), 6))
    x = range(len(df))
    erro = [df.r_dp - ic_inf, ic_sup - df.r_dp]
    ax.errorbar(x, df.r_dp, yerr=erro, fmt='o-', color='#2166ac',
                capsize=4, linewidth=2, markersize=7)
    ax.axhline(0, color='grey', linewidth=1, linestyle='--')
    ax.set_xticks(list(x))
    ax.set_xticklabels(df.periodo, rotation=45, ha='right')
    ax.set_ylabel(r'$r_{dp}$ (assortatividade fuzzy)')
    ax.set_title('Assortatividade por alinhamento com o governo, por mandato\n(IC 95%, s_fuzzy trapezoidal)')
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=150)
    print(f"Gráfico salvo em {caminho_saida}")


if __name__ == '__main__':
    print("Assortatividade fuzzy por mandato — Câmara dos Deputados\n")

    todos_os_anos = sorted({a for anos in MANDATOS.values() for a in anos})
    max_autores_global = calcular_max_autores_global(PASTA, todos_os_anos)
    print()

    resultados = []
    for rotulo, anos in MANDATOS.items():
        r = analisar_mandato(PASTA, rotulo, anos, max_autores_global)
        if r:
            resultados.append(r)
            print(f"  {rotulo:28s} r_dp={r['r_dp']:+.3f}  p={r['p_perm_fmt']:>9s} ({r['significativo']})")

    df = pd.DataFrame(resultados)
    df.to_csv('/content/assortatividade_por_mandato.csv', index=False)

    cols_principal = ['periodo', 'n_nos_rede', 'S_obs', 'S_esp', 'sqrt_V',
                       'r_dp', 'IC_95', 'p_perm_fmt', 'significativo']
    cols_limiares = ['periodo', 'favor_p50', 'favor_p75', 'contra_p50', 'contra_p75',
                      'n_governo', 'n_oposicao', 'n_centrao']

    print("\n" + "─" * 90)
    print(f"Tabela 1 — Assortatividade (IC 95% de S_esp; p_perm: teste de permutação,")
    print(f"H0='categoria sem relação com a rede', N={N_PERMUTACOES:,}, alpha={ALPHA})")
    print("─" * 90)
    print(df[cols_principal].rename(columns={'p_perm_fmt': 'p_perm'}).to_string(index=False))

    print("\n" + "─" * 90)
    print("Tabela 2 — Limiares trapezoidais (p50/p75 de P_f e P_c) e categoria dominante")
    print("─" * 90)
    print(df[cols_limiares].to_string(index=False))

    print(f"\nCorte de outliers da rede (fixo, 2003-2025): {max_autores_global:.0f} autores/proposição")
    print("Tabela completa (com densidade e demais colunas) salva em "
          "/content/assortatividade_por_mandato.csv")

    plot_evolucao_r(df, '/content/evolucao_r_por_mandato.png')



