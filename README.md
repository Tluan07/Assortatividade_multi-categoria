# Assortatividade Multi-Categoria

Códigos usados na dissertação de mestrado para calcular o índice de
assortatividade multi-categoria ($r$) em diferentes tipos de rede.

## Estrutura

| Arquivo | O que faz |
|---|---|
| `assortatividade.py` | Módulo principal: as funções de similaridade e o cálculo do índice $r$. Os outros scripts importam deste arquivo. |
| `deezer_analise.py` | Aplica o índice às redes sociais do Deezer (Romênia, Croácia, Hungria). |
| `coautoria_crisp_sem_peso.py` | Aplica o índice a redes de coautoria, sem peso. |
| `coautoria_crisp_com_peso.py` | Mesma rede de coautoria, agora com peso pela recência da colaboração. |
| `cocitacao_crisp.py` | Aplica o índice a uma rede de cocitação. |
| `cocitacao_fuzzy.py` | Mesma rede de cocitação, com categorias fuzzy. |

## Como usar

Cada script pode ser executado sem depender dos outros scripts de aplicação — mas todos importam funções de `assortatividade.py`, que precisa estar na mesma pasta. Direto da pasta principal:

```bash
python deezer_analise.py
python coautoria_crisp_sem_peso.py
python coautoria_crisp_com_peso.py
python cocitacao_crisp.py
python cocitacao_fuzzy.py
```

## Requisitos

- Python 3.10 ou superior
- Biblioteca `networkx` (`pip install networkx`)

## Dados

Os scripts de coautoria e cocitação usam dados exportados da
[Web of Science](https://www.webofscience.com). O script do Deezer
usa dados públicos disponíveis em
[snap.stanford.edu/data/gemsec-Deezer.html](https://snap.stanford.edu/data/gemsec-Deezer.html).
