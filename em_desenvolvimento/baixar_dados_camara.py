# -*- coding: utf-8 -*-
"""
baixar_dados_camara.py

Baixa automaticamente os arquivos de dados abertos da Câmara dos
Deputados necessários para camara_diagnostico.py e
camara_assortatividade.py — votacoesVotos, votacoesOrientacoes e
proposicoesAutores, um arquivo por ano.

Fonte pública, sem necessidade de login:
https://dadosabertos.camara.leg.br/swagger/api.html#staticfile

Uso:
    python baixar_dados_camara.py
(ou, no Colab: from baixar_dados_camara import baixar_dados_camara;
 baixar_dados_camara())
"""

import os
import urllib.request
import urllib.error

PASTA_PADRAO = './dados/camara_deputados'
ANOS_PADRAO = list(range(2003, 2026))
RECURSOS = ['votacoesVotos', 'votacoesOrientacoes', 'proposicoesAutores']
URL_BASE = 'https://dadosabertos.camara.leg.br/arquivos/{recurso}/xlsx/{recurso}-{ano}.xlsx'


def baixar_dados_camara(pasta=PASTA_PADRAO, anos=ANOS_PADRAO, forcar=False):
    """Baixa (se ainda não existirem) os arquivos .xlsx de votos,
    orientações de voto e autoria de proposições, ano a ano.
    Alguns anos/recursos podem não existir (ex: proposicoesAutores só
    existe a partir de um certo ano) — nesses casos, o download falha
    silenciosamente com um aviso, e o restante continua normalmente."""
    os.makedirs(pasta, exist_ok=True)
    total, ja_existiam, baixados, ausentes = 0, 0, 0, 0

    for recurso in RECURSOS:
        for ano in anos:
            total += 1
            nome_arquivo = f"{recurso}-{ano}.xlsx"
            caminho = os.path.join(pasta, nome_arquivo)
            if os.path.exists(caminho) and not forcar:
                ja_existiam += 1
                continue

            url = URL_BASE.format(recurso=recurso, ano=ano)
            try:
                urllib.request.urlretrieve(url, caminho)
                baixados += 1
                print(f"  OK  {nome_arquivo}")
            except urllib.error.HTTPError as e:
                ausentes += 1
                if os.path.exists(caminho):
                    os.remove(caminho)  # remove página de erro salva por engano
                print(f"  --  {nome_arquivo} indisponível ({e.code}), pulando")
            except Exception as e:
                ausentes += 1
                print(f"  ERRO {nome_arquivo}: {e}")

    print(f"\nResumo: {total} arquivos verificados | "
          f"{ja_existiam} já existiam | {baixados} baixados agora | "
          f"{ausentes} indisponíveis na fonte.")
    print(f"Dados em: {pasta}")


if __name__ == '__main__':
    baixar_dados_camara()
