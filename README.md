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

Cada script roda sozinho, direto da pasta principal:

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

O `deezer_analise.py` **baixa os dados automaticamente** na primeira
execução (dataset público do SNAP/GEMSEC, sem login). Não precisa baixar
nada manualmente.

Os scripts de coautoria e cocitação usam dados da Web of Science, obtidos
por acesso institucional (CAFe) e protegidos por termos de uso que proíbem
redistribuição pública — por isso **não há download automático** para
esses dois. É preciso ter acesso próprio à Web of Science e refazer a
mesma busca (documentada na dissertação) para gerar os arquivos esperados.
