# -*- coding: utf-8 -*-
"""
camara_deputados.py

Aplicação à Câmara dos Deputados brasileira. Cada deputado recebe graus
de pertinência fuzzy a três grupos — Governo, Oposição e Centrão —
calculados a partir do seu alinhamento com as orientações de voto do
governo. O alinhamento é resumido num ÚNICO eixo:

    diff(deputado) = P_f(deputado) - P_c(deputado)   ∈ [-1, 1]

(P_f e P_c = proporção de votações em que o deputado votou a favor /
contra a orientação do governo). Os limiares (percentis 20, 40, 60 e 80
de diff) são calculados UMA ÚNICA VEZ sobre todos os deputados de todos
os mandatos juntos — não por mandato — de modo que "ser Governo"
signifique o mesmo em 2003 e em 2023 e os mandatos possam ser comparados
na mesma régua (mesma ideia dos limiares fixos de Curto/Médio/Longo na
rede de citação).

As três pertinências formam uma partição trapezoidal desse eixo
(Oposição | Centrão | Governo) e somam exatamente 1. Por isso só existem
5 posições possíveis: vértice Oposição, aresta Oposição–Centrão, vértice
Centrão, aresta Governo–Centrão e vértice Governo.

A rede é a de coautoria de proposições legislativas, com peso igual ao
número de proposições assinadas em comum e um corte de outliers
(percentil 99 de autores/proposição) calculado uma única vez sobre toda
a base 2003-2025.

Referência: Seção 4.2.6 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os arquivos
votacoesVotos-{ano}.xlsx / votacoesOrientacoes-{ano}.xlsx /
proposicoesAutores-{ano}.xlsx em PASTA (baixados automaticamente do
release do GitHub). Também requer pandas e openpyxl, usados apenas por
este script.
"""

import os, random, statistics, warnings, zipfile, urllib.request, shutil
from collections import defaultdict, Counter
from itertools import combinations
import pandas as pd
import networkx as nx

from assortatividade import calcular_r

# O openpyxl avisa, a cada leitura, que a planilha "não tem estilo padrão".
# É só ruído (não afeta nenhum dado); silenciamos para não poluir a saída.
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# Caminhos e URL do release do GitHub
PASTA        = './dados/camara'
URL_RELEASE  = 'https://github.com/Tluan07/Assortatividade_multi-categoria/releases/download/v1.0/dados_camara.zip'
N_AMOSTRAS   = 10_000
SEMENTE      = 42

# Participação mínima (fração das votações com orientação do governo em
# que o deputado votou Sim/Não) para entrar na análise. 0.0 = sem filtro
# (comportamento original). Um valor como 0.10 exclui suplentes de
# passagem, cujo diff ≈ 0 por AUSÊNCIA seria lido como "Centrão".
MIN_PARTICIPACAO = 0.0


def baixar_e_extrair_dados(pasta=PASTA, url=URL_RELEASE):
    os.makedirs(pasta, exist_ok=True)
    caminho_zip = os.path.join(pasta, 'dados_camara.zip')

    # Verifica se já existem os arquivos .xlsx diretamente na pasta
    ja_baixado = any(nome.startswith('proposicoesAutores') and nome.endswith('.xlsx')
                     for nome in os.listdir(pasta))

    if not ja_baixado:
        print(f"Baixando dados da Câmara de {url} ...")
        try:
            urllib.request.urlretrieve(url, caminho_zip)
            print("Extraindo arquivos ZIP...")
            with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                zip_ref.extractall(pasta)
        finally:
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)

        # Move os arquivos caso tenham sido extraídos dentro de uma subpasta
        # (ex: ./dados/camara/dados_camara/...)
        for item in os.listdir(pasta):
            subpasta = os.path.join(pasta, item)
            if os.path.isdir(subpasta):
                for f in os.listdir(subpasta):
                    shutil.move(os.path.join(subpasta, f), os.path.join(pasta, f))
                os.rmdir(subpasta)

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

CATEGORIAS_ORDEM = ['Vértice Oposição', 'Aresta Oposição–Centrão', 'Vértice Centrão',
                    'Aresta Governo–Centrão', 'Vértice Governo']


def _ler(pasta, prefixo, ano, colunas):
    f = os.path.join(pasta, f'{prefixo}-{ano}.xlsx')
    return pd.read_excel(f, usecols=colunas) if os.path.exists(f) else None


# -- Alinhamento com o governo: P_f (favor) e P_c (contra) ------------------
def carregar_favor_contra(pasta, anos):
    """Concatena os anos do período e devolve {deputado_id: proporção}
    de votos a favor/contra a orientação do governo, sobre o total de
    votações válidas do período inteiro (recontagem agregada, não média
    de percentuais anuais — evita distorcer anos com poucas votações).

    Cuidados: ids sempre int (os arquivos de votos e de autoria precisam
    casar); votos e orientações duplicados são removidos; votações em que
    o governo tem orientações contraditórias são descartadas."""
    vs, ors = [], []
    for ano in anos:
        v = _ler(pasta, 'votacoesVotos', ano, ['idVotacao', 'deputado_id', 'voto'])
        o = _ler(pasta, 'votacoesOrientacoes', ano, ['idVotacao', 'siglaBancada', 'orientacao'])
        if v is not None and o is not None:
            vs.append(v); ors.append(o)
    if not vs:
        return {}, {}

    votos  = pd.concat(vs, ignore_index=True).dropna(subset=['deputado_id'])
    votos['deputado_id'] = votos['deputado_id'].astype(int)
    votos  = votos.drop_duplicates(['idVotacao', 'deputado_id'])
    orient = pd.concat(ors, ignore_index=True)

    gov = orient[orient.siglaBancada.isin(['Governo', 'GOV.']) & orient.orientacao.isin(['Sim', 'Não'])]
    n_orient = gov.groupby('idVotacao').orientacao.nunique()
    conflitantes = n_orient[n_orient > 1].index
    if len(conflitantes):
        print(f"  [aviso] {len(conflitantes)} votações com orientação conflitante do governo descartadas")
    gov = gov[~gov.idVotacao.isin(conflitantes)].drop_duplicates('idVotacao')
    gov = gov[['idVotacao', 'orientacao']].rename(columns={'orientacao': 'orientacao_governo'})
    total_votacoes = gov.idVotacao.nunique()
    if total_votacoes == 0:
        return {}, {}

    # Só as linhas de voto que existem (sem produto cartesiano deputados x votações);
    # quem não votou numa votação simplesmente não soma nem a favor nem contra.
    v = votos[votos.voto.isin(['Sim', 'Não'])].merge(gov, on='idVotacao', how='inner')
    v['favor'] = (v.voto == v.orientacao_governo)
    r = v.groupby('deputado_id').agg(favor=('favor', 'sum'), validos=('favor', 'size'))
    r = r.reindex(votos.deputado_id.unique(), fill_value=0)
    r['contra'] = r.validos - r.favor

    if MIN_PARTICIPACAO > 0:
        r = r[r.validos / total_votacoes >= MIN_PARTICIPACAO]

    return (r.favor / total_votacoes).to_dict(), (r.contra / total_votacoes).to_dict()


# -- Limiares GLOBAIS (todos os mandatos juntos) ------------------------------
def calcular_limiares_globais(pasta, mandatos):
    """Concatena diff = P_f - P_c de todos os deputados de todos os mandatos
    e devolve os percentis 20/40/60/80 dessa distribuição conjunta. Devolve
    também o cache {mandato: (pct_favor, pct_contra)} para não reler os
    arquivos depois."""
    cache, todas = {}, []
    for rotulo, anos in mandatos.items():
        pct_favor, pct_contra = carregar_favor_contra(pasta, anos)
        cache[rotulo] = (pct_favor, pct_contra)
        todas.extend(pct_favor[d] - pct_contra.get(d, 0.0) for d in pct_favor)

    s = pd.Series(todas)
    limiares = {'p20': s.quantile(0.20), 'p40': s.quantile(0.40),
                'p60': s.quantile(0.60), 'p80': s.quantile(0.80)}
    return limiares, cache, len(todas)


# -- Pertinências fuzzy: partição trapezoidal do eixo único -------------------
def _rampa_desc(x, a, b):
    """1 até a, desce linearmente até 0 em b."""
    if b <= a:
        return 1.0 if x <= a else 0.0
    return min(1.0, max(0.0, (b - x) / (b - a)))


def _rampa_asc(x, a, b):
    """0 até a, sobe linearmente até 1 em b."""
    if b <= a:
        return 1.0 if x > a else 0.0
    return min(1.0, max(0.0, (x - a) / (b - a)))


def pertinencias_eixo_unico(diff, limiares):
    """mu_Oposição = 1 até p20, cai a 0 em p40; mu_Governo = 0 até p60, sobe
    a 1 em p80; mu_Centrão = 1 - mu_Oposição - mu_Governo (rampa em
    [p20,p40], platô em [p40,p60], rampa em [p60,p80]). A soma é sempre 1,
    inclusive quando há empates entre percentis."""
    o = _rampa_desc(diff, limiares['p20'], limiares['p40'])
    g = _rampa_asc(diff, limiares['p60'], limiares['p80'])
    c = max(0.0, 1.0 - o - g)
    return {'Governo': g, 'Oposição': o, 'Centrão': c}


def categoria(mu):
    """Com o eixo único só existem 5 posições (a soma é 1 e no máximo duas
    pertinências são simultaneamente não-nulas)."""
    g, o, c = mu['Governo'], mu['Oposição'], mu['Centrão']
    if g == 1.0: return 'Vértice Governo'
    if o == 1.0: return 'Vértice Oposição'
    if c == 1.0: return 'Vértice Centrão'
    if o > 0:    return 'Aresta Oposição–Centrão'
    return 'Aresta Governo–Centrão'


def s_fuzzy(mu_i, mu_j):
    """Simétrica por construção — não precisa da média (func(i,j)+func(j,i))/2
    usada para similaridades assimétricas como s_dir."""
    return max(mu_i[c] * mu_j[c] for c in ('Governo', 'Oposição', 'Centrão'))


# -- Rede de coautoria de proposições, com corte global de outliers ---------
_CACHE_AUTORES = {}


def _autores_ano(pasta, ano):
    """Autores-deputados de um ano (lido uma única vez), com id int."""
    if ano not in _CACHE_AUTORES:
        d = _ler(pasta, 'proposicoesAutores', ano, ['idProposicao', 'codTipoAutor', 'idDeputadoAutor'])
        if d is not None:
            d = d[(d.codTipoAutor == 10000) & d.idDeputadoAutor.notna()].copy()
            d['idDeputadoAutor'] = d['idDeputadoAutor'].astype(int)
            d = d[['idProposicao', 'idDeputadoAutor']]
        _CACHE_AUTORES[ano] = d
    return _CACHE_AUTORES[ano]


def calcular_max_autores_global(pasta, todos_os_anos):
    """Corte de outliers (percentil 99 de autores/proposição) calculado
    uma única vez sobre toda a base 2003-2025 — não por mandato — para
    que o critério de 'proposição normal' não mude de tamanho a cada
    período e as redes continuem estruturalmente comparáveis entre si
    (ex.: PECs, que exigem assinatura de 1/3 da Câmara, aparecem em
    todos os mandatos, mas só distorcem a densidade se o corte for
    relativo)."""
    partes = [d for ano in todos_os_anos if (d := _autores_ano(pasta, ano)) is not None]
    if not partes:
        raise FileNotFoundError(
            f"Nenhum arquivo 'proposicoesAutores-{{ano}}.xlsx' encontrado em '{os.path.abspath(pasta)}' "
            f"para os anos {todos_os_anos[0]}-{todos_os_anos[-1]}. Confira o valor de PASTA no topo do "
            f"script e se os arquivos foram salvos exatamente com esse nome."
        )
    dep = pd.concat(partes, ignore_index=True)
    n_autores = dep.groupby('idProposicao')['idDeputadoAutor'].nunique()
    return n_autores.quantile(0.99)


def construir_rede(pasta, anos, attrs_todos, max_autores):
    """attrs_todos: {deputado_id: pertinências}, já calculado antes de
    chamar esta função. max_autores: corte global (ver acima).
    O nº de nós descartados por falta de atributo fica em G.graph['sem_atributo']."""
    partes = [d for ano in anos if (d := _autores_ano(pasta, ano)) is not None]
    if not partes:
        return nx.Graph(), {}

    dep = pd.concat(partes, ignore_index=True)
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
    G.graph['sem_atributo'] = G.number_of_nodes() - len(attrs)
    G.remove_nodes_from([n for n in list(G.nodes()) if n not in attrs])
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
    forca  = dict(G.degree(weight='peso'))
    forcas = [forca[no] for no in nos]
    cats   = [attrs[no] for no in nos]
    # cum_weights pré-calculado: mesmo resultado de random.choices(weights=...),
    # mas sem refazer a soma acumulada a cada sorteio.
    acum = []; total = 0
    for f in forcas:
        total += f; acum.append(total)
    indices = range(len(nos))
    amostras = []; tentativas = 0
    while len(amostras) < n and tentativas < n * 10:
        tentativas += 1
        i = random.choices(indices, cum_weights=acum)[0]
        j = random.choices(indices, cum_weights=acum)[0]
        if i != j:
            amostras.append(func(cats[i], cats[j]))
    if not amostras:
        return 0.0, 0.0
    return statistics.mean(amostras), statistics.stdev(amostras) if len(amostras) > 1 else 0.0


# -- Análise por mandato ------------------------------------------------------
def analisar_mandato(pasta, rotulo, anos, max_autores, attrs_todos):
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
    if G.graph.get('sem_atributo'):
        print(f"  Coautores sem dados de votação (descartados): {G.graph['sem_atributo']:,}")
    print(f"\n  {'Função':<12}{'S_obs':>8}{'S_esp':>8}{'dp':>9}{'r_desv':>9}{'IC_inf':>9}{'IC_sup':>9}")
    print(f"  {'-'*63}")
    print(f"  {'s_fuzzy':<12}{S_obs:>8.4f}{S_esp:>8.4f}{dp:>9.4f}{r:>9.4f}{ic_inf:>9.4f}{ic_sup:>9.4f}")

    return {'periodo': rotulo, 'n_nos': G.number_of_nodes(), 'n_arestas': G.number_of_edges(),
            'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp, 'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}


if __name__ == '__main__':
    # 1) limiares globais fixos (uma única régua para todos os mandatos)
    limiares, cache, n_total = calcular_limiares_globais(PASTA, MANDATOS)
    print(f"\nLimiares globais de diff = P_f - P_c  (n = {n_total:,} deputado-mandatos):")
    print(f"  p20 = {limiares['p20']:.4f}   p40 = {limiares['p40']:.4f}   "
          f"p60 = {limiares['p60']:.4f}   p80 = {limiares['p80']:.4f}")

    # 2) pertinências por mandato + distribuição nas 5 posições
    attrs_por_mandato, linhas = {}, []
    for rotulo in MANDATOS:
        pct_favor, pct_contra = cache[rotulo]
        if not pct_favor:
            print(f"  [aviso] {rotulo}: sem votações válidas de governo — pulando")
            continue
        attrs = {d: pertinencias_eixo_unico(pct_favor[d] - pct_contra.get(d, 0.0), limiares)
                 for d in pct_favor}
        attrs_por_mandato[rotulo] = attrs

        cont = Counter(categoria(mu) for mu in attrs.values())
        linha = {'mandato': rotulo, 'n': len(attrs)}
        linha.update({c: round(100 * cont.get(c, 0) / len(attrs), 1) for c in CATEGORIAS_ORDEM})
        linhas.append(linha)

    print("\nDistribuição nas 5 posições (% dos deputados por mandato):")
    print(pd.DataFrame(linhas).set_index('mandato').to_string())

    # 3) rede de coautoria + assortatividade por mandato
    todos_os_anos = sorted({a for anos in MANDATOS.values() for a in anos})
    max_autores_global = calcular_max_autores_global(PASTA, todos_os_anos)
    print(f"\nCorte global de outliers (p99 autores/proposição, 2003-2025): {max_autores_global:.0f}")

    resultados = {}
    for rotulo, anos in MANDATOS.items():
        if rotulo not in attrs_por_mandato:
            continue
        try:
            resultados[rotulo] = analisar_mandato(PASTA, rotulo, anos, max_autores_global,
                                                  attrs_por_mandato[rotulo])
        except FileNotFoundError as e:
            print(f"[ERRO] {rotulo}: {e}")

    print(f"\n{'='*78}")
    print("  RESUMO — r_desvio [IC 95%], por mandato")
    print(f"{'='*78}")
    for rotulo, res in resultados.items():
        if res:
            print(f"  {rotulo:<28} r = {res['r_desvio']:>7.4f}  [{res['ic_inf']:.4f}, {res['ic_sup']:.4f}]")

    pd.DataFrame([r for r in resultados.values() if r]).set_index('periodo') \
        .to_csv('resultados_camara.csv')
    print("\nSalvo em resultados_camara.csv")
