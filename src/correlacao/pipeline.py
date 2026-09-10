"""
Etapa de correlacao: aplica as colunas I a N e separa as duas planilhas.

Entrada: o DataFrame das 7 colunas ja carregadas da exportacao do SAP.
Saida: 'correlacionadas' (NG != Validacao) e 'validacao' (NG == Validacao,
com a coluna 'motivo'), mais um resumo com os controlos.
"""

from dataclasses import dataclass

import pandas as pd

from src.correlacao import regras
from src.correlacao.chaves import canonizar_serie, montar_chave_serie
from src.infra.logger import setup_logger

logger = setup_logger(__name__)

# Colunas B a H da 'Base Exportacao', na ordem em que la aparecem.
COLUNAS_ENTRADA = [
    "Account",
    "Amount in local currency",
    "Document Number",
    "Posting Date",
    "Text",
    "Cost Center",
    "WBS element",
]

# Colunas I a N. A coluna O ('Exclusao por Tr') fica de fora nesta etapa.
COLUNAS_CALCULADAS = [
    "GL Description",
    "NG",
    "Descrição NG",
    "Custo / Despesa Adm",
    "Validação",
    "Conciliação",
]

COLUNAS_SAIDA = COLUNAS_ENTRADA + COLUNAS_CALCULADAS

# Nomes do export bruto da FAGLB03 -> nomes da 'Base Exportacao'. O SAP escreve
# 'Amount in Local Currency' e 'WBS Element'; a planilha usa outra caixa.
RENOMEACAO_EXPORT = {
    "Amount in Local Currency": "Amount in local currency",
    "WBS Element": "WBS element",
}

COLUNA_AMOUNT = "Amount in local currency"

# Tolerancia do fechamento contabil, em reais. O somatorio de floats do SAP
# fecha em ~1e-10, nao em zero exato.
TOLERANCIA_FECHAMENTO = 0.005


@dataclass
class ResultadoCorrelacao:
    correlacionadas: pd.DataFrame
    validacao: pd.DataFrame
    resumo: dict


class FalhaDeControle(Exception):
    """Um controlo obrigatorio nao passou. O processamento nao deve continuar."""


def preparar_entrada(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajusta o DataFrame do export ao contrato das 7 colunas B a H.

    Renomeia as colunas cuja caixa difere e descarta as que a 'Base Exportacao'
    nao usa (Local Currency, Profit Center). Falha alto se faltar alguma das 7 -
    coluna em falta e mudanca de layout, nao caso a contornar.
    """
    entrada = df.rename(columns=RENOMEACAO_EXPORT)
    em_falta = [c for c in COLUNAS_ENTRADA if c not in entrada.columns]
    if em_falta:
        raise FalhaDeControle(
            f"Colunas ausentes na exportacao: {em_falta}. "
            f"Recebidas: {list(df.columns)}"
        )
    return entrada[COLUNAS_ENTRADA].copy()


def aplicar_colunas_calculadas(entrada: pd.DataFrame, mestras) -> pd.DataFrame:
    """
    Calcula I a N para TODAS as linhas recebidas.

    Nao ha delimitacao por intervalo de linhas em lado nenhum: o que entra e o
    que sai. Foi um intervalo fixo (formulas ate a linha 6796, dados ate a
    6834) que deixou 38 linhas sem correlacao e sem aviso no Excel.
    """
    df = entrada.copy()
    chaves = montar_chave_serie(df["Cost Center"], df["Account"])
    contas = canonizar_serie(df["Account"])

    df["GL Description"] = [mestras.gl_description(c) or "" for c in contas]

    linhas = [mestras.linha_de_para(k) for k in chaves]

    df["NG"] = [
        regras.VALIDACAO if l is None or not l["NG"] else l["NG"] for l in linhas
    ]
    df["Descrição NG"] = [
        regras.VALIDACAO if l is None or not l["Descrição NG"] else l["Descrição NG"]
        for l in linhas
    ]

    wbs = canonizar_serie(df["WBS element"])
    df["Custo / Despesa Adm"] = [
        regras.DESPESA
        if w.startswith(regras.PREFIXO_WBS_DESPESA)
        else (
            regras.VALIDACAO
            if l is None or not l["Custo / Despesa Adm"]
            else l["Custo / Despesa Adm"]
        )
        for w, l in zip(wbs, linhas)
    ]

    df["Validação"] = [
        regras.validacao(a, c, mestras)
        for a, c in zip(df[COLUNA_AMOUNT], df["Account"])
    ]

    df["Conciliação"] = [
        regras.SEM_CONCILIACAO if l is None or not l["Conciliação"] else l["Conciliação"]
        for l in linhas
    ]

    return df[COLUNAS_SAIDA]


def separar(calculado: pd.DataFrame) -> tuple:
    """
    Corta pela coluna J: correlacionadas sao as linhas com NG != 'Validacao'.

    A coluna M tambem pode valer 'Validacao', com outro significado (lookup na
    'Base GL'), e vai nas duas planilhas - mas nao define a separacao.
    """
    faltantes = calculado["NG"] == regras.VALIDACAO
    correlacionadas = calculado[~faltantes].reset_index(drop=True)

    validacao = calculado[faltantes].reset_index(drop=True)
    validacao["motivo"] = [
        regras.motivo_validacao(cc, conta)
        for cc, conta in zip(validacao["Cost Center"], validacao["Account"])
    ]
    return correlacionadas, validacao


def verificar_controles(
    entrada: pd.DataFrame,
    correlacionadas: pd.DataFrame,
    validacao: pd.DataFrame,
) -> dict:
    """
    Controlos obrigatorios. Conservacao falha alto; fechamento so avisa.

    Conservacao de linhas e de valor sao invariantes do proprio processamento:
    se falharem, o codigo esta errado e nao ha resultado a entregar. O
    fechamento contabil em zero e uma propriedade dos *dados* - uma exportacao
    desequilibrada e um problema a montante, que deve ser visto mas nao e o
    codigo que o pode corrigir.
    """
    n_entrada = len(entrada)
    n_saida = len(correlacionadas) + len(validacao)
    if n_saida != n_entrada:
        raise FalhaDeControle(
            f"Conservacao de linhas violada: entrada={n_entrada}, "
            f"correlacionadas={len(correlacionadas)} + validacao={len(validacao)} "
            f"= {n_saida}."
        )

    soma_entrada = float(entrada[COLUNA_AMOUNT].sum())
    soma_saida = float(correlacionadas[COLUNA_AMOUNT].sum()) + float(
        validacao[COLUNA_AMOUNT].sum()
    )
    if abs(soma_saida - soma_entrada) > TOLERANCIA_FECHAMENTO:
        raise FalhaDeControle(
            f"Conservacao de valor violada: entrada={soma_entrada:.2f}, "
            f"saidas={soma_saida:.2f}."
        )

    fecha = abs(soma_entrada) <= TOLERANCIA_FECHAMENTO
    if not fecha:
        logger.warning(
            f"FECHAMENTO CONTABIL: a soma de '{COLUNA_AMOUNT}' na base completa "
            f"e R$ {soma_entrada:,.2f}, nao zero. Um razao equilibrado fecha em "
            "zero - confirme o filtro da exportacao antes de usar este resultado."
        )

    return {
        "linhas_entrada": n_entrada,
        "linhas_correlacionadas": len(correlacionadas),
        "linhas_validacao": len(validacao),
        "soma_entrada": soma_entrada,
        "soma_saidas": soma_saida,
        "fechamento_em_zero": fecha,
    }


def registrar_resumo(resultado: ResultadoCorrelacao) -> None:
    """Contagem por NG, por motivo e por classificacao de M. Sem valores individuais."""
    r = resultado.resumo
    logger.info("=== Resumo da correlacao ===")
    logger.info(f"  linhas de entrada      : {r['linhas_entrada']}")
    logger.info(f"  correlacionadas (NG ok): {r['linhas_correlacionadas']}")
    logger.info(f"  em validacao (NG vazio): {r['linhas_validacao']}")
    logger.info(f"  soma Amount (entrada)  : R$ {r['soma_entrada']:,.2f}")
    logger.info(f"  fecha em zero          : {r['fechamento_em_zero']}")

    todas = pd.concat(
        [resultado.correlacionadas, resultado.validacao], ignore_index=True
    )

    logger.info("  contagem por NG (top 15 + Validacao):")
    for valor, n in todas["NG"].value_counts().head(15).items():
        logger.info(f"    {valor}: {n}")

    logger.info("  contagem por motivo (fila de validacao):")
    if len(resultado.validacao):
        for valor, n in resultado.validacao["motivo"].value_counts().items():
            logger.info(f"    {valor}: {n}")
    else:
        logger.info("    (nenhuma linha em validacao)")

    logger.info("  contagem por Validacao (coluna M):")
    for valor, n in todas["Validação"].value_counts().items():
        logger.info(f"    {valor}: {n}")


def executar(df_export: pd.DataFrame, mestras) -> ResultadoCorrelacao:
    """Ponto de entrada da etapa: entrada -> duas planilhas + resumo."""
    entrada = preparar_entrada(df_export)
    logger.info(f"Correlacao a processar {len(entrada)} linhas de entrada.")

    calculado = aplicar_colunas_calculadas(entrada, mestras)
    correlacionadas, validacao = separar(calculado)
    resumo = verificar_controles(entrada, correlacionadas, validacao)
    resumo["origem_tabelas_mestras"] = getattr(mestras, "origem", {})

    resultado = ResultadoCorrelacao(correlacionadas, validacao, resumo)
    registrar_resumo(resultado)
    return resultado
