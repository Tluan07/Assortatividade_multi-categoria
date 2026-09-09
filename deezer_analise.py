# -*- coding: utf-8 -*-
"""
deezer_analise.py

Aplicação às redes sociais do Deezer (RO, HR, HU), em três níveis de
granularidade de gêneros musicais:
  Nível 1: os 84 gêneros originais da base.
  Nível 2: 14 grupos de gêneros aparentados (ex.: "Rock", "Jazz").
  Nível 3: 6 grandes famílias musicais (ex.: "Rock & Pop", "Urbano").

Estimação de S_esp por Monte Carlo (N = 10.000 amostras) e intervalos
de confiança de 95%, para cada nível, em cada país.

Referência: Seção 4.2.4 da dissertação.
Requer: assortatividade.py no mesmo diretório, e os arquivos
<PAIS>_edges.csv / <PAIS>_genres.json em DATA_DIR (ver README.txt).
"""

import os, json, csv, math, random, statistics, tarfile, urllib.request
import networkx as nx

from assortatividade import s_min, s_max, s_jaccard, s_dir, calcular_r

DATA_DIR   = './dados/deezer'
PAISES     = ['RO', 'HR', 'HU']
N_AMOSTRAS = 10_000
SEMENTE    = 42

URL_SNAP = 'https://snap.stanford.edu/data/gemsec_deezer_dataset.tar.gz'


def baixar_dados_deezer(pasta=DATA_DIR):
    """Baixa e extrai o dataset público do Deezer (SNAP/GEMSEC), caso os
    arquivos ainda não existam em `pasta`. Não requer login: os dados são
    públicos. Fonte: https://snap.stanford.edu/data/gemsec-Deezer.html"""
    ja_existem = all(
        os.path.exists(os.path.join(pasta, f"{p}_{sufixo}"))
        for p in PAISES for sufixo in ('edges.csv', 'genres.json')
    )
    if ja_existem:
        return

    os.makedirs(pasta, exist_ok=True)
    caminho_tar = os.path.join(pasta, '_gemsec_deezer_dataset.tar.gz')
    print(f"Baixando dataset Deezer de {URL_SNAP} ...")
    urllib.request.urlretrieve(URL_SNAP, caminho_tar)

    print("Extraindo...")
    with tarfile.open(caminho_tar) as tar:
        tar.extractall(pasta)
    os.remove(caminho_tar)

    # O tar.gz extrai numa subpasta própria; move os arquivos para `pasta`
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            if nome.endswith(('_edges.csv', '_genres.json')) and raiz != pasta:
                os.rename(os.path.join(raiz, nome), os.path.join(pasta, nome))
    print("Dados do Deezer prontos em", pasta)

SIM_FUNCS = [('s_min', s_min), ('s_max', s_max), ('s_Jaccard', s_jaccard), ('s_dir', s_dir)]


# -- Nível 2: 84 gêneros originais -> 14 grupos ------------------------------
GENERO_NIVEL2 = {
    # Blues
    'Acoustic Blues': 'Blues', 'Blues': 'Blues', 'Chicago Blues': 'Blues',
    'Classic Blues': 'Blues', 'Country Blues': 'Blues', 'Electric Blues': 'Blues',
    # Jazz
    'Instrumental jazz': 'Jazz', 'Jazz': 'Jazz', 'Jazz Hip Hop': 'Jazz', 'Vocal jazz': 'Jazz',
    # Clássica/Erudita
    'Baroque': 'Classica', 'Classical': 'Classica', 'Classical Period': 'Classica',
    'Opera': 'Classica', 'Musicals': 'Classica',
    # Trilhas/Mídia
    'Film Scores': 'Trilhas', 'Films/Games': 'Trilhas', 'Game Scores': 'Trilhas',
    'Soundtracks': 'Trilhas', 'TV Soundtracks': 'Trilhas', 'TV shows & movies': 'Trilhas',
    # Infantil
    'Kids': 'Infantil', 'Kids & Family': 'Infantil', 'Nursery Rhymes': 'Infantil',
    'Stories': 'Infantil', 'Comedy': 'Infantil',
    # Country/Folk
    'Alternative Country': 'CountryFolk', 'Bluegrass': 'CountryFolk', 'Country': 'CountryFolk',
    'Folk': 'CountryFolk', 'Singer & Songwriter': 'CountryFolk', 'Urban Cowboy': 'CountryFolk',
    # R&B/Soul
    'Contemporary R&B': 'RnBSoul', 'Contemporary Soul': 'RnBSoul', 'Old school soul': 'RnBSoul',
    'Oldschool R&B': 'RnBSoul', 'R&B': 'RnBSoul', 'Soul & Funk': 'RnBSoul',
    # Hip-Hop/Rap
    'Dirty South': 'HipHop', 'East Coast': 'HipHop', 'Electro Hip Hop': 'HipHop',
    'Grime': 'HipHop', 'Old School': 'HipHop', 'Rap/Hip Hop': 'HipHop', 'West Coast': 'HipHop',
    # Eletrônica/Dance
    'Chill Out/Trip-Hop/Lounge': 'Eletronica', 'Dance': 'Eletronica', 'Dancefloor': 'Eletronica',
    'Disco': 'Eletronica', 'Dub': 'Eletronica', 'Dubstep': 'Eletronica', 'Electro': 'Eletronica',
    'Electro Pop/Electro Rock': 'Eletronica', 'Techno/House': 'Eletronica', 'Trance': 'Eletronica',
    # Reggae/Caribenho
    'Dancehall/Ragga': 'Reggae', 'Reggae': 'Reggae', 'Ska': 'Reggae', 'Tropical': 'Reggae',
    # Rock
    'Alternative': 'Rock', 'Hard Rock': 'Rock', 'Indie Rock': 'Rock',
    'Indie Rock/Rock pop': 'Rock', 'Metal': 'Rock', 'Rock': 'Rock', 'Rock & Roll/Rockabilly': 'Rock',
    # Pop
    'Indie Pop': 'Pop', 'Indie Pop/Folk': 'Pop', 'International Pop': 'Pop',
    'Modern': 'Pop', 'Pop': 'Pop', 'Romantic': 'Pop',
    # Música do Mundo
    'African Music': 'Mundo', 'Asian Music': 'Mundo', 'Bolero': 'Mundo', 'Bollywood': 'Mundo',
    'Brazilian Music': 'Mundo', 'Corridos': 'Mundo', 'Indian Music': 'Mundo',
    'Latin Music': 'Mundo', 'Norteño': 'Mundo', 'Ranchera': 'Mundo',
    # Espiritualidade/Outros
    'Spirituality & Religion': 'Outros', 'Sports': 'Outros',
}

# -- Nível 3: 14 grupos do Nível 2 -> 6 grandes famílias ---------------------
GRUPO_NIVEL3 = {
    'Classica': 'EruditaTrilhas', 'Jazz': 'EruditaTrilhas', 'Trilhas': 'EruditaTrilhas',
    'Rock': 'RockPop', 'Pop': 'RockPop',
    'HipHop': 'Urbano', 'RnBSoul': 'Urbano',
    'Eletronica': 'Eletronica',
    'Blues': 'RaizesMundo', 'CountryFolk': 'RaizesMundo', 'Reggae': 'RaizesMundo', 'Mundo': 'RaizesMundo',
    'Infantil': 'InfantilOutros', 'Outros': 'InfantilOutros',
}

GENERO_NIVEL3 = {genero: GRUPO_NIVEL3[grupo2] for genero, grupo2 in GENERO_NIVEL2.items()}

NIVEIS = {
    1: ('84 gêneros originais', None),
    2: ('14 grupos de gêneros',  GENERO_NIVEL2),
    3: ('6 grandes famílias',    GENERO_NIVEL3),
}


def aplicar_nivel(attrs, mapa):
    """Reagrupa as categorias de cada usuário segundo o mapa gênero->grupo.
    mapa=None mantém os gêneros originais (Nível 1)."""
    if mapa is None:
        return attrs
    novo = {}
    for no, generos in attrs.items():
        grupos = frozenset(mapa[g] for g in generos if g in mapa)
        if grupos:
            novo[no] = grupos
    return novo


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


def analisar_pais_nivel(pais, attrs_base, G, nivel):
    rotulo, mapa = NIVEIS[nivel]
    attrs = aplicar_nivel(attrs_base, mapa)
    G_n = G.subgraph([n for n in G.nodes() if n in attrs]).copy()

    tamanhos = [len(attrs[n]) for n in G_n.nodes()]
    n_cats   = len({c for n in G_n.nodes() for c in attrs[n]})

    print(f"\n{'═'*80}")
    print(f"  Deezer — {pais} — Nível {nivel} ({rotulo})")
    print(f"{'═'*80}")
    print(f"  Nós:                   {G_n.number_of_nodes():,}")
    print(f"  Arestas:               {G_n.number_of_edges():,}")
    print(f"  Categorias distintas:  {n_cats}")
    print(f"  Categorias por nó — min: {min(tamanhos)}  max: {max(tamanhos)}  média: {statistics.mean(tamanhos):.2f}")

    print(f"\n  {'Função':<12} {'S_obs':>7} {'S_esp':>7} {'dp':>8} {'r_desv':>8} {'IC_inf':>8} {'IC_sup':>8}")
    print(f"  {'─'*70}")
    res = {}
    for nome, func in SIM_FUNCS:
        S_obs = calcular_s_obs(G_n, attrs, func)
        S_esp, dp_mc = estimar_s_esp(G_n, attrs, func)
        dp = math.sqrt(S_esp * (1 - S_esp)) if nome in ('s_min', 's_max') else dp_mc
        r, ic_inf, ic_sup = calcular_r(S_obs, S_esp, dp, N_AMOSTRAS)
        print(f"  {nome:<12} {S_obs:>7.4f} {S_esp:>7.4f} {dp:>8.4f} {r:>8.4f} {ic_inf:>8.4f} {ic_sup:>8.4f}")
        res[nome] = {'S_obs': S_obs, 'S_esp': S_esp, 'dp': dp, 'r_desvio': r, 'ic_inf': ic_inf, 'ic_sup': ic_sup}
    return res


def analisar_pais(pais):
    G, attrs_base = construir_rede(pais, DATA_DIR)
    resultado_por_nivel = {}
    for nivel in (1, 2, 3):
        resultado_por_nivel[nivel] = analisar_pais_nivel(pais, attrs_base, G, nivel)
    return resultado_por_nivel


if __name__ == '__main__':
    baixar_dados_deezer()

    todos = {}
    for pais in PAISES:
        try:
            todos[pais] = analisar_pais(pais)
        except FileNotFoundError as e:
            print(f"\n[ERRO] {e}")

    print(f"\n{'═'*80}")
    print("  RESUMO — r_desvio  [IC 95%], por nível de granularidade")
    print(f"{'═'*80}")
    for nivel in (1, 2, 3):
        rotulo, _ = NIVEIS[nivel]
        print(f"\n  --- Nível {nivel}: {rotulo} ---")
        print(f"  {'Função':<12}", end="")
        for pais in PAISES:
            print(f" {pais:>24}", end="")
        print()
        print(f"  {'─'*80}")
        for nome, _ in SIM_FUNCS:
            print(f"  {nome:<12}", end="")
            for pais in PAISES:
                r = todos.get(pais, {}).get(nivel, {}).get(nome, {})
                if r:
                    print(f"  {r['r_desvio']:>7.4f} [{r['ic_inf']:.4f},{r['ic_sup']:.4f}]", end="")
                else:
                    print(f"  {'N/A':>24}", end="")
            print()
