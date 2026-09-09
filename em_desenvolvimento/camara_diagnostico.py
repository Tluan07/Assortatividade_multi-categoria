# -*- coding: utf-8 -*-
"""
Câmara dos Deputados — diagnóstico de votações por ano/mandato
e reconstrução do gráfico de percentis (agora por período, não só por ano).

Reconstrói dois pedaços de código perdidos do notebook original:
  1) a contagem de votações válidas do governo por ano (usada para decidir
     se dá pra calcular homofilia ano a ano ou só por mandato);
  2) o gráfico de evolução dos percentis 75/90 de Favor/Contra, agora
     generalizado para também poder ser calculado por MANDATO (bloco de
     anos), e não só ano a ano.

Uso:
    - Rode a Parte 1 primeiro. Ela só imprime números — serve pra decidir
      se algum ano tem votações de menos para ser confiável isoladamente.
    - A Parte 2 calcula os percentis das duas formas (ano a ano e por
      mandato) e gera os dois gráficos, lado a lado, pra comparação visual.
"""

import os, warnings
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

PASTA = '/content/sample_data/camara_deputados'
ANOS = list(range(2003, 2026))

# ── Definição dos mandatos ──────────────────────────────────────────────
# Blocos de 4 anos, exceto o corte em torno do impeachment. Como os
# arquivos são por ano inteiro (sem data exata da votação disponível no
# código atual), 2016 fica como período isolado — nem colado no bloco de
# Dilma (2015) nem no de Temer (2017-2018). Ajustem aqui se decidirem
# fundir 2016 a um dos lados, ou dividir por data quando tiverem essa
# informação disponível.
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
# PARTE 1 — Diagnóstico: quantas votações válidas de governo existem
#           por ano e por mandato (decide granularidade da homofilia)
# ══════════════════════════════════════════════════════════════════════

def contar_votacoes_ano(pasta, ano):
    """Lê um ano e devolve o número de votações válidas do governo,
    o número de deputados presentes na base, e o número de deputados
    que de fato votaram pelo menos uma vez. Retorna None se faltar
    arquivo ou não houver votação válida de governo."""
    fv = os.path.join(pasta, f'votacoesVotos-{ano}.xlsx')
    fo = os.path.join(pasta, f'votacoesOrientacoes-{ano}.xlsx')
    if not (os.path.exists(fv) and os.path.exists(fo)):
        return None
    try:
        votos = pd.read_excel(fv)
        orient = pd.read_excel(fo)
    except Exception as e:
        print(f"  [aviso] {ano}: arquivo inválido/corrompido ({e}) — pulando")
        return None

    gov = orient[orient.siglaBancada.isin(['Governo', 'GOV.']) & orient.orientacao.isin(['Sim', 'Não'])]
    n_votacoes = gov.idVotacao.nunique()
    if n_votacoes == 0:
        return None

    deputados = votos.deputado_id.unique()
    votaram = votos[votos.voto.isin(['Sim', 'Não'])].deputado_id.nunique()

    return {
        'ano': ano,
        'votacoes_validas_governo': n_votacoes,
        'deputados_na_base': len(deputados),
        'deputados_que_votaram': votaram,
    }


def diagnostico_por_ano(pasta, anos):
    linhas = [r for a in anos if (r := contar_votacoes_ano(pasta, a)) is not None]
    return pd.DataFrame(linhas)


def diagnostico_por_mandato(df_ano, mandatos):
    """Agrega o diagnóstico anual em blocos de mandato: soma as votações
    válidas nos anos do bloco e reporta quantos desses anos têm dado."""
    linhas = []
    for periodo, anos in mandatos.items():
        sub = df_ano[df_ano.ano.isin(anos)]
        if sub.empty:
            continue
        linhas.append({
            'periodo': periodo,
            'anos_com_dado': f"{sub.ano.min()}-{sub.ano.max()}" if len(sub) > 1 else str(sub.ano.iloc[0]),
            'n_anos_com_dado': len(sub),
            'n_anos_esperados': len(anos),
            'votacoes_validas_total': int(sub.votacoes_validas_governo.sum()),
            'votacoes_validas_media_ano': round(sub.votacoes_validas_governo.mean(), 1),
        })
    return pd.DataFrame(linhas)


# ══════════════════════════════════════════════════════════════════════
# PARTE 2 — Percentis de Favor/Contra: ano a ano E por mandato
# ══════════════════════════════════════════════════════════════════════

def pct_favor_contra_periodo(pasta, anos):
    """Generaliza carregar_favor_contra: concatena os anos do período
    (um único ano também funciona) e devolve pct_favor / pct_contra por
    deputado, calculados sobre TODAS as votações válidas do período
    inteiro (não é média dos percentuais anuais — é recontagem agregada,
    o que é o correto para não distorcer anos com poucas votações)."""
    vs, ors = [], []
    for ano in anos:
        fv = os.path.join(pasta, f'votacoesVotos-{ano}.xlsx')
        fo = os.path.join(pasta, f'votacoesOrientacoes-{ano}.xlsx')
        if os.path.exists(fv) and os.path.exists(fo):
            try:
                vs.append(pd.read_excel(fv))
                ors.append(pd.read_excel(fo))
            except Exception as e:
                print(f"  [aviso] {ano}: arquivo inválido/corrompido ({e}) — pulando")
    if not vs:
        return None, None, 0

    votos, orient = pd.concat(vs, ignore_index=True), pd.concat(ors, ignore_index=True)
    gov = orient[orient.siglaBancada.isin(['Governo', 'GOV.']) & orient.orientacao.isin(['Sim', 'Não'])]
    gov = gov[['idVotacao', 'orientacao']].rename(columns={'orientacao': 'orientacao_governo'})
    total_votacoes = gov.idVotacao.nunique()
    if total_votacoes == 0:
        return None, None, 0

    deputados = votos.deputado_id.unique()
    base = pd.MultiIndex.from_product([deputados, gov.idVotacao], names=['deputado_id', 'idVotacao']).to_frame(index=False)
    base = base.merge(gov, on='idVotacao', how='left')
    base = base.merge(votos[['idVotacao', 'deputado_id', 'voto']], on=['idVotacao', 'deputado_id'], how='left')

    base['favor'] = (base.voto.isin(['Sim', 'Não'])) & (base.voto == base.orientacao_governo)
    base['contra'] = (base.voto.isin(['Sim', 'Não'])) & (base.voto != base.orientacao_governo)

    r = base.groupby('deputado_id').agg(favor=('favor', 'sum'), contra=('contra', 'sum'))
    pct_favor = r.favor / total_votacoes
    pct_contra = r.contra / total_votacoes
    return pct_favor, pct_contra, total_votacoes


def percentis_periodo(pct_favor, pct_contra):
    return {
        'favor_p50': pct_favor.quantile(0.50),
        'favor_p75': pct_favor.quantile(0.75),
        'contra_p50': pct_contra.quantile(0.50),
        'contra_p75': pct_contra.quantile(0.75),
    }


def montar_tabela_percentis(pasta, blocos):
    """blocos: dict {rótulo: [anos]} — funciona tanto para {2003:[2003], ...}
    (um ano por bloco) quanto para MANDATOS (vários anos por bloco)."""
    linhas = []
    for rotulo, anos in blocos.items():
        pct_favor, pct_contra, n_vot = pct_favor_contra_periodo(pasta, anos)
        if pct_favor is None:
            continue
        p = percentis_periodo(pct_favor, pct_contra)
        p['periodo'] = rotulo
        p['n_votacoes'] = n_vot
        p['n_deputados'] = len(pct_favor)
        linhas.append(p)
    cols = ['periodo', 'n_votacoes', 'n_deputados', 'favor_p50', 'favor_p75', 'contra_p50', 'contra_p75']
    return pd.DataFrame(linhas)[cols] if linhas else pd.DataFrame(columns=cols)


def plot_percentis(df, titulo, caminho_saida, rotulo_x='periodo'):
    fig, ax = plt.subplots(figsize=(max(12, len(df) * 0.6), 7))
    x = range(len(df))
    ax.plot(x, df.favor_p75, marker='o', color='#2166ac', linewidth=2, label='Favor — p75')
    ax.plot(x, df.favor_p50, marker='o', color='#67a9cf', linewidth=2, label='Favor — p50')
    ax.plot(x, df.contra_p75, marker='s', color='#b2182b', linewidth=2, label='Contra — p75')
    ax.plot(x, df.contra_p50, marker='s', color='#ef8a62', linewidth=2, label='Contra — p50')
    ax.set_ylabel('Grau de pertinência (percentil calculado naquele período)')
    ax.set_xlabel('Período')
    ax.set_title(titulo)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(list(x))
    ax.set_xticklabels(df[rotulo_x], rotation=45, ha='right')
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=150)
    print(f"Salvo em {caminho_saida}")


# ══════════════════════════════════════════════════════════════════════
# Execução
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("═" * 78)
    print("  PARTE 1 — Diagnóstico de votações válidas de governo")
    print("═" * 78)
    df_diag_ano = diagnostico_por_ano(PASTA, ANOS)
    print("\nPor ano:")
    print(df_diag_ano.to_string(index=False))
    df_diag_ano.to_csv('/content/diagnostico_votacoes_por_ano.csv', index=False)

    df_diag_mandato = diagnostico_por_mandato(df_diag_ano, MANDATOS)
    print("\nPor mandato:")
    print(df_diag_mandato.to_string(index=False))
    df_diag_mandato.to_csv('/content/diagnostico_votacoes_por_mandato.csv', index=False)

    anos_com_dado = set(df_diag_ano.ano)
    anos_faltantes = [a for a in ANOS if a not in anos_com_dado]
    print(f"\nAnos sem dado (0 votações válidas de governo ou arquivo ausente): {anos_faltantes}")

    print("\n" + "═" * 78)
    print("  PARTE 2 — Percentis de Favor/Contra")
    print("═" * 78)

    blocos_por_ano = {a: [a] for a in ANOS}
    df_pct_ano = montar_tabela_percentis(PASTA, blocos_por_ano)
    print("\nPor ano:")
    print(df_pct_ano.to_string(index=False))
    plot_percentis(df_pct_ano, 'Percentis 50/75 — Favor e Contra, por ANO',
                    '/content/curvas_favor_contra_por_ano.png', rotulo_x='periodo')

    df_pct_mandato = montar_tabela_percentis(PASTA, MANDATOS)
    print("\nPor mandato:")
    print(df_pct_mandato.to_string(index=False))
    plot_percentis(df_pct_mandato, 'Percentis 50/75 — Favor e Contra, por MANDATO',
                    '/content/curvas_favor_contra_por_mandato.png', rotulo_x='periodo')

