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

Intervalo de confiança (método Delta)
-------------------------------------
Como o desvio padrão dp também é estimado com a mesma amostra de N pares,
r_hat = (S_obs - S_bar)/s depende de duas estimativas (S_bar e s), e

    Var(r_hat) ≈ (1/N) * [ 1 + r*gamma1 + (r**2/4) * (beta2 - 1) ],

em que gamma1 é a assimetria e beta2 a curtose (sem subtrair 3) da
distribuição de S sob o modelo nulo. IC 95%: r_hat ± 1.96 * SE.

 - Similaridades binárias (s_min, s_max): S ~ Bernoulli(p), p = S_esp, e
   gamma1 = (1-2p)/sqrt(p(1-p)),  beta2 = 1/(p(1-p)) - 3.
 - Similaridades graduadas (Jaccard, direcionada, fuzzy): gamma1 e beta2 são
   estimados empiricamente nas N amostras de Monte Carlo.
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


# -- Momentos da distribuição de S ---------------------------------------
def momentos_amostra(amostras):
    """Devolve (média, desvio padrão amostral, assimetria, curtose) das
    amostras de similaridade. A curtose NÃO subtrai 3 (normal = 3).
    Se a variância é nula, assimetria e curtose não são definidas e
    devolvem-se 0 e 3 (valores da normal); nesse caso dp = 0 e r = 0."""
    n = len(amostras)
    if n == 0:
        return 0.0, 0.0, 0.0, 3.0
    media = sum(amostras) / n
    if n < 2:
        return media, 0.0, 0.0, 3.0
    dp = math.sqrt(sum((x - media) ** 2 for x in amostras) / (n - 1))
    m2 = sum((x - media) ** 2 for x in amostras) / n
    if m2 <= 0:
        return media, 0.0, 0.0, 3.0
    m3 = sum((x - media) ** 3 for x in amostras) / n
    m4 = sum((x - media) ** 4 for x in amostras) / n
    return media, dp, m3 / m2 ** 1.5, m4 / m2 ** 2


def momentos_bernoulli(p):
    """(assimetria, curtose) de uma Bernoulli(p); curtose sem subtrair 3."""
    if p <= 0 or p >= 1:
        return 0.0, 3.0
    q = p * (1 - p)
    return (1 - 2 * p) / math.sqrt(q), 1 / q - 3


# -- Índice de assortatividade multi-categoria ---------------------------
def erro_padrao_r(r, n, gamma1, beta2):
    """SE(r_hat) = sqrt{ (1/n) [1 + r*gamma1 + (r^2/4)(beta2 - 1)] }
    (método Delta). Como beta2 >= gamma1^2 + 1, o radicando é >= 0."""
    radicando = 1 + r * gamma1 + (r ** 2 / 4) * (beta2 - 1)
    return math.sqrt(max(radicando, 0.0) / n)


def calcular_r(S_obs, S_esp, dp, n, gamma1=0.0, beta2=3.0, binaria=False):
    """r = (S_obs - S_esp) / dp  |  IC 95%: r ± 1.96 * SE(r), com SE pelo
    método Delta (leva em conta que S_esp e dp são estimados na mesma amostra).

    n       : nº de amostras de Monte Carlo.
    gamma1  : assimetria de S (estimada nas amostras, se não binária).
    beta2   : curtose de S, sem subtrair 3.
    binaria : se True (s_min, s_max), gamma1 e beta2 são calculados pelas
              fórmulas da Bernoulli(p = S_esp), ignorando os argumentos.

    Convenção: se dp <= 0, r = 0 (Eq. do índice na dissertação); o IC
    continua sendo ± 1.96/√n."""
    if binaria:
        gamma1, beta2 = momentos_bernoulli(S_esp)
    if dp <= 0:
        m = 1.96 / math.sqrt(n)
        return 0.0, -m, m
    r = (S_obs - S_esp) / dp
    m = 1.96 * erro_padrao_r(r, n, gamma1, beta2)
    return r, r - m, r + m
