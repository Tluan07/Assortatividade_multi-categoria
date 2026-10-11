# Assortatividade Multi-Categoria

Códigos usados na dissertação de mestrado para calcular o índice de
assortatividade multi-categoria ($r$) em diferentes tipos de rede.

## Estrutura

| Arquivo                       | O que faz |
| ----------------------------- | --------- |
| `assortatividade.py`          | Módulo principal: as funções de similaridade e o cálculo do índice $r$. Os outros scripts importam deste arquivo. |
| `deezer_analise.py`           | Aplica o índice às redes sociais do Deezer (Romênia, Croácia, Hungria). |
| `coautoria_crisp_sem_peso.py` | Aplica o índice a redes de coautoria, sem peso. |
| `coautoria_crisp_com_peso.py` | Mesma rede de coautoria, agora com peso pela recência da colaboração. |
| `cocitacao_crisp.py`          | Aplica o índice à rede de citação (grafo dirigido construído pelos DOI das referências). O nome do arquivo mantém o termo "cocitação". |
| `cocitacao_fuzzy.py`          | Mesma rede de citação, com categorias fuzzy (Curto/Médio/Longo, pelo número de páginas). |
| `camara_deputados.py`         | Aplica o índice fuzzy à Câmara dos Deputados, por mandato — alinhamento político (Governo/Oposição/Centrão). |

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

Cada script de aplicação define para si `calcular_s_obs` e `estimar_s_esp`
(S_obs e a estimativa de S_esp por Monte Carlo); `assortatividade.py` traz as
funções de similaridade e `calcular_r`.

## Requisitos

- Python 3.10 ou superior
- `networkx` (`pip install networkx`) — usado por todos os scripts
- `pandas` e `openpyxl` (`pip install pandas openpyxl`) — usados apenas
  por `camara_deputados.py`, para ler os arquivos `.xlsx` da Câmara

Tudo pode ser instalado com `pip install -r requirements.txt`.

## Dados

Ao rodar um script, os dados necessários são baixados automaticamente para
`./dados/` (relativo ao diretório de execução): os pacotes da release `v1.0`
deste repositório (Web of Science e Câmara) e, para o Deezer, o arquivo
público do SNAP. Importar os módulos não dispara downloads.

Os scripts de coautoria e cocitação usam dados exportados da
[Web of Science](https://www.webofscience.com). O script do Deezer usa
dados públicos disponíveis em
[snap.stanford.edu/data/gemsec-Deezer.html](https://snap.stanford.edu/data/gemsec-Deezer.html).
O script `camara_deputados.py` usa dados públicos da Câmara dos
Deputados, disponíveis em
[dadosabertos.camara.leg.br](https://dadosabertos.camara.leg.br/)
(arquivos `votacoesVotos-{ano}.xlsx`, `votacoesOrientacoes-{ano}.xlsx`
e `proposicoesAutores-{ano}.xlsx`, um trio por ano).

## Saídas e reprodutibilidade

Os scripts imprimem as tabelas no terminal; `camara_deputados.py` também
grava `resultados_camara.csv`. Em todos, N = 10.000 amostras de Monte Carlo e
semente fixa (`SEMENTE = 42`), então os resultados são reprodutíveis.
