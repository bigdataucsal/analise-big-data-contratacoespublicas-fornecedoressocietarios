"""Regras de negocio da Trilha 3, sem leitura de arquivo e sem banco.

Cada modulo corresponde a uma regra de docs/regras-de-negocio.md e existe para
que a regra tenha um unico lugar onde mora e um teste que a prove. Os scripts
do pipeline importam daqui em vez de reimplementar o criterio.
"""

from . import (
    anonimizacao,
    concentracao,
    controle,
    elegibilidade,
    genero,
    identificadores,
    proxy_racial,
    qualificacoes,
    sancoes,
)

__all__ = [
    "anonimizacao",
    "concentracao",
    "controle",
    "elegibilidade",
    "genero",
    "identificadores",
    "proxy_racial",
    "qualificacoes",
    "sancoes",
]
