"""
Normalizacao de chaves de correlacao SAP <-> NG.

Existe um unico motivo para este modulo: no Excel a mesma conta contabil esta
gravada ora como numero, ora como texto (169/75 em 'Base GL'; 2.419/866 em
'Base De-Para'). O PROCV compara tipos, nao valores, por isso a busca falha em
silencio. Aqui os dois lados passam pela *mesma* funcao antes de qualquer
comparacao - e nenhum lookup deste pacote aceita valor que nao tenha passado
por ela.
"""

import math
import re

import pandas as pd

# Separador de milhar que o Excel pode ter deixado no texto ("1.234" / "1,234").
_MILHAR = re.compile(r"(?<=\d)[., \s](?=\d{3}\b)")


def canonizar(valor) -> str:
    """
    Devolve a forma canonica em texto de uma conta ou centro de custo.

    Regras, nesta ordem:
      - vazio (None, NaN, string em branco) -> ""
      - numero inteiro (int, ou float com parte decimal nula) -> sem ".0"
      - texto -> sem espacos nas pontas e sem separador de milhar

    Zeros a esquerda sao preservados: '00123' continua '00123', porque num
    plano de contas isso pode ser significativo. Por consequencia, '00123' e
    '123' NAO sao a mesma chave - se um dia a origem passar a truncar zeros,
    isto aparece como falta de correlacao, nunca como correlacao errada.
    """
    if valor is None:
        return ""
    if isinstance(valor, float):
        if math.isnan(valor):
            return ""
        if valor.is_integer():
            return str(int(valor))
        return repr(valor)
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int):
        return str(valor)
    if valor is pd.NaT:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()
    if not texto:
        return ""
    # So remove separador de milhar se o que sobra e mesmo um numero; assim
    # nomes de centro de custo como 'PRJBR4052' ficam intactos.
    sem_milhar = _MILHAR.sub("", texto)
    if sem_milhar.lstrip("+-").isdigit():
        texto = sem_milhar
    # '140050.0' vindo como texto e o mesmo numero que 140050.
    if re.fullmatch(r"[+-]?\d+\.0+", texto):
        texto = texto.split(".")[0]
    return texto


def canonizar_serie(serie: pd.Series) -> pd.Series:
    """Aplica canonizar() a uma coluna inteira, devolvendo dtype string."""
    return serie.map(canonizar).astype("string")


def montar_chave(centro_custo, conta) -> str:
    """
    Chave de correlacao: centro de custo concatenado com a conta, sem separador.

    Equivale ao '=C&D' da coluna 'Chave' da 'Base De-Para'. Centro de custo
    vazio e caso legitimo - a chave fica sendo so a conta, e a tabela mestra
    tem 67 linhas cadastradas exatamente assim.
    """
    return canonizar(centro_custo) + canonizar(conta)


def montar_chave_serie(centros_custo: pd.Series, contas: pd.Series) -> pd.Series:
    return (canonizar_serie(centros_custo) + canonizar_serie(contas)).astype("string")
