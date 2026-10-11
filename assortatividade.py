# -*- coding: utf-8 -*-
"""
assortatividade.py

Módulo principal: implementação das quatro funções de similaridade
(s_min, s_max, s_Jaccard, s_dir) e do índice de assortatividade multi-categoria
r = (S_obs - S_esp) / dp, com intervalo de confiança de 95%.

Referência: Seções 3.1.1 a 3.1.4 e 3.1.7 da dissertação.
Este módulo não roda sozinho — é importado pelos scripts de aplicação
(deezer_analise.py, coautoria_*.py, cocitacao_*.py e camara_deputados.py).
Obs.: as funções calcular_s_obs e estimar_s_esp (S_obs e a estimativa de
S_esp por Monte Carlo) são definidas em cada script de aplicação.
"""

import math

# -- Funções de similaridade --------------------------------------------
def s_min(xi, xj):
    return 1 if xi & xj else 0

def s_max(xi, xj):
    return 1 if xi == xj and xi else 0

def s_jaccard(xi, xj):
    u = xi | xj
    return len(xi & xj) / len(u) if u else 0

def s_dir(xi, xj):
    return len(xi & xj) / len(xj) if xj else 0


# -- Índice de assortatividade multi-categoria ---------------------------
def calcular_r(S_obs, S_esp, dp, n):
    """r = (S_obs - S_esp) / dp  |  IC 95%: r ± 1.96/√n"""
    if dp <= 0:
        return 0.0, 0.0, 0.0
    r = (S_obs - S_esp) / dp
    m = 1.96 / math.sqrt(n)
    return r, r - m, r + m
