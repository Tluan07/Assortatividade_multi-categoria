Repositório de códigos — Dissertação de Mestrado
Índice de Assortatividade Multi-Categoria

ESTRUTURA
---------
codigos/
|-- assortatividade.py            Módulo principal (funções de similaridade + índice r)
|-- deezer_analise.py             Deezer: 3 redes sociais (RO, HR, HU), sem granularidade
|-- coautoria_crisp_sem_peso.py   Coautoria WoS: sem peso
|-- coautoria_crisp_com_peso.py   Coautoria WoS: com peso (tercil de recência)
|-- cocitacao_crisp.py            Cocitação WoS: categorias crisp (áreas WC)
|-- cocitacao_fuzzy.py            Cocitação WoS: categorias fuzzy (Curto/Médio/Longo)
|-- em_desenvolvimento/           Exemplo da Câmara dos Deputados (AINDA NÃO FINALIZADO,
|                                  não faz parte do Apêndice A da dissertação)
+-- README.txt                    Este arquivo

COMO RODAR
----------
Cada script é independente. A partir da pasta codigos/:

    python deezer_analise.py
    python coautoria_crisp_sem_peso.py
    python coautoria_crisp_com_peso.py
    python cocitacao_crisp.py
    python cocitacao_fuzzy.py

DADOS
-----
Os scripts de coautoria e cocitação esperam os arquivos brutos da Web of
Science em ./dados/wos/<pasta_do_topico>/*.txt (exportação direta da
plataforma Web of Science: https://www.webofscience.com).

O script deezer_analise.py espera ./dados/deezer/<PAIS>_edges.csv e
./dados/deezer/<PAIS>_genres.json, disponíveis publicamente em
https://snap.stanford.edu/data/gemsec-Deezer.html

DEPENDÊNCIAS
------------
Python 3.10+
    networkx >= 3.0
    matplotlib >= 3.5, pandas, numpy   (apenas em em_desenvolvimento/)
    statistics, math, random, os, json, csv, re, itertools, collections
    (módulos padrão da biblioteca Python)
