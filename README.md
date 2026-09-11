# Assortatividade Multi-Categoria

Códigos usados na dissertação de mestrado para calcular o índice de
assortatividade multi-categoria ($r$) em diferentes tipos de rede.

## Estrutura

| Arquivo                       | O que faz                                                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `assortatividade.py`          | Módulo principal: as funções de similaridade e o cálculo do índice $r$. Os outros scripts importam deste arquivo. |
| `deezer_analise.py`           | Aplica o índice às redes sociais do Deezer (Romênia, Croácia, Hungria).                                           |
| `coautoria_crisp_sem_peso.py` | Aplica o índice a redes de coautoria, sem peso.                                                                   |
| `coautoria_crisp_com_peso.py` | Mesma rede de coautoria, agora com peso pela recência da colaboração.                                             |
| `cocitacao_crisp.py`          | Aplica o índice a uma rede de cocitação.                                                                          |
| `cocitacao_fuzzy.py`          | Mesma rede de cocitação, com categorias fuzzy.                                                                    |
| `camara_deputados.py`         | Aplica o índice fuzzy à Câmara dos Deputados, por mandato — alinhamento político (Governo/Oposição/Centrão).

## Como usar

Cada script roda sozinho, direto da pasta principal:

```
python deezer_analise.py
python coautoria_crisp_sem_peso.py
python coautoria_crisp_com_peso.py
python cocitacao_crisp.py
python cocitacao_fuzzy.py
python camara_deputados.py
```

## Requisitos

- Python 3.10 ou superior
- `networkx` (`pip install networkx`) — usado por todos os scripts
- `pandas` e `openpyxl` (`pip install pandas openpyxl`) — usados apenas
  por `camara_deputados.py`, para ler os arquivos `.xlsx` da Câmara

## Dados

Os scripts de coautoria e cocitação usam dados exportados da
[Web of Science](https://www.webofscience.com). O script do Deezer usa
dados públicos disponíveis em
[snap.stanford.edu/data/gemsec-Deezer.html](https://snap.stanford.edu/data/gemsec-Deezer.html).
O script `camara_deputados.py` usa dados públicos da Câmara dos
Deputados, disponíveis em
[dadosabertos.camara.leg.br](https://dadosabertos.camara.leg.br/)
(arquivos `votacoesVotos-{ano}.xlsx`, `votacoesOrientacoes-{ano}.xlsx`
e `proposicoesAutores-{ano}.xlsx`, um trio por ano).
