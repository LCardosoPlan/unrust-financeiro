"""
Colunas calculadas I a N da aba 'Base Exportacao', como funcoes puras.

Cada regra recebe valores ja canonizados e as tabelas mestras, e devolve o
valor de uma coluna. Nenhuma delas toca em DataFrame - e o que as torna
testaveis linha a linha. A coluna O ('Exclusao por Tr') nao esta aqui: a
formula original aponta para um intervalo apagado (#REF!) e sera tratada
noutra etapa.
"""

from src.correlacao.chaves import canonizar, montar_chave

# Marcador de lookup falhado. Aparece em J, K, L e M - mas com significados
# diferentes: em J/K/L significa 'chave ausente na Base De-Para', em M
# significa 'conta ausente na Base GL'. Sao conjuntos distintos de linhas.
VALIDACAO = "Validação"

# Ausencia de classificacao na 'Base GL' significa lancamento de base contabil.
BASE_CONTABIL = "Base Contábil"

# Amount == 0 nunca entra na correlacao.
EXCLUSAO = "Exclusão"

# Prefixo de WBS que forca 'Despesa' independentemente da tabela mestra.
PREFIXO_WBS_DESPESA = "BR01471"

DESPESA = "Despesa"

# Sem correlacao registada na coluna 'Conciliacao'.
SEM_CONCILIACAO = "N"


def gl_description(conta, mestras) -> str:
    """Coluna I - descricao da conta no plano de contas SAP."""
    valor = mestras.gl_description(canonizar(conta))
    return "" if valor is None else valor


def ng(centro_custo, conta, mestras) -> str:
    """Coluna J - conta NG correspondente. E este o criterio de corte das saidas."""
    linha = mestras.linha_de_para(montar_chave(centro_custo, conta))
    if linha is None:
        return VALIDACAO
    valor = linha["NG"]
    return valor if valor else VALIDACAO


def descricao_ng(centro_custo, conta, mestras) -> str:
    """Coluna K - descricao da conta NG."""
    linha = mestras.linha_de_para(montar_chave(centro_custo, conta))
    if linha is None:
        return VALIDACAO
    valor = linha["Descrição NG"]
    return valor if valor else VALIDACAO


def custo_despesa_adm(wbs, centro_custo, conta, mestras) -> str:
    """
    Coluna L - natureza do lancamento.

    Precedencia deliberada: o prefixo de WBS vence o lookup. Um lancamento em
    BR01471 e 'Despesa' mesmo que a tabela mestra diga outra coisa, e mesmo
    que a chave nem sequer esteja cadastrada.
    """
    if canonizar(wbs).startswith(PREFIXO_WBS_DESPESA):
        return DESPESA
    linha = mestras.linha_de_para(montar_chave(centro_custo, conta))
    if linha is None:
        return VALIDACAO
    valor = linha["Custo / Despesa Adm"]
    return valor if valor else VALIDACAO


def validacao(amount, conta, mestras) -> str:
    """
    Coluna M - tratamento previsto para a conta.

    Precedencia deliberada: valor zero vence a classificacao. Um lancamento de
    valor nulo e 'Exclusao' independentemente do que diga a 'Base GL'.

    A classificacao em branco na 'Base GL' significa 'Base Contabil' - por isso
    o teste e contra None (conta ausente) e contra "" (conta presente, sem
    classificacao), nunca contra zero. No Excel os dois casos eram
    indistinguiveis porque o PROCV devolve 0 para celula vazia.
    """
    if amount is not None and float(amount) == 0:
        return EXCLUSAO
    classe = mestras.classificacao(canonizar(conta))
    if classe is None:
        return VALIDACAO
    return classe if classe else BASE_CONTABIL


def conciliacao(centro_custo, conta, mestras) -> str:
    """
    Coluna N - marca de conciliacao.

    AVISO: a origem ('Base De-Para' col. I) esta vazia em praticamente todas as
    linhas, portanto esta coluna sai quase toda como "N". A regra esta
    implementada como especificada, mas a coluna nao carrega hoje informacao
    util e nao deve embasar decisao ate a tabela mestra ser preenchida.
    """
    linha = mestras.linha_de_para(montar_chave(centro_custo, conta))
    if linha is None:
        return SEM_CONCILIACAO
    valor = linha["Conciliação"]
    return valor if valor else SEM_CONCILIACAO


# --- Classificacao da fila de trabalho -------------------------------------

MOTIVO_CC_VAZIO = "cost_center_vazio"
MOTIVO_PRJBRBRA1 = "prjbrbra1_sem_sufixo"
MOTIVO_COMBINACAO = "combinacao_ausente"

# A tabela mestra usa PRJBRBRA1C e PRJBRBRA1D; o export traz PRJBRBRA1 puro.
CENTRO_CUSTO_SEM_SUFIXO = "PRJBRBRA1"


def motivo_validacao(centro_custo, conta) -> str:
    """
    Porque e que esta linha caiu na fila de validacao.

    So se aplica a linhas com NG == 'Validacao'. As tres causas sao mutuamente
    exclusivas e verificadas por especificidade: centro de custo vazio, depois
    centro de custo sem sufixo, e por fim a causa generica.
    """
    cc = canonizar(centro_custo)
    if not cc:
        return MOTIVO_CC_VAZIO
    if cc == CENTRO_CUSTO_SEM_SUFIXO:
        return MOTIVO_PRJBRBRA1
    return MOTIVO_COMBINACAO
