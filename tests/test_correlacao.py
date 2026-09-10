"""
Testes da etapa de correlacao.

Um teste por ponto de tratamento da especificacao (1 a 7) e um por controlo
obrigatorio. Os dados sao sinteticos: nenhum valor real da organizacao entra
na suite.
"""

import pandas as pd
import pytest

from src.correlacao import pipeline, regras
from src.correlacao.chaves import canonizar, montar_chave
from src.correlacao.tabelas_mestras import COLUNA_CLASSIFICACAO, TabelasMestras
from src.correlacao.vocabulario import normalizar_custo_despesa


# --- Fixtures ---------------------------------------------------------------


def _mestras(gl_linhas, dp_linhas):
    """Constroi TabelasMestras a partir de tuplos, como o loader faria."""
    gl = pd.DataFrame(gl_linhas, columns=["SAP", "GL Description", COLUNA_CLASSIFICACAO])
    dp = pd.DataFrame(
        dp_linhas,
        columns=[
            "Chave",
            "Cost Center",
            "SAP",
            "NG",
            "Descrição NG",
            "Custo / Despesa Adm",
            "Conciliação",
        ],
    )
    contagem = dp["Chave"].value_counts()
    duplicadas = dp[dp["Chave"].isin(contagem[contagem > 1].index)]
    return TabelasMestras(gl=gl, de_para=dp, chaves_duplicadas=duplicadas)


@pytest.fixture
def mestras():
    return _mestras(
        gl_linhas=[
            ("140050", "Other Receivables", ""),          # classificacao vazia
            ("663500", "Training", "Analisar"),
            ("110028", "Leasehold", "Exclusão"),
        ],
        dp_linhas=[
            ("PRJBR4052140050", "PRJBR4052", "140050", "1.1.2", "Recebiveis", "Custo", ""),
            ("140050", "", "140050", "1.1.9", "Recebiveis s/ CC", "Despesa", ""),
            ("PRJBRBRA1C663500", "PRJBRBRA1C", "663500", "3.1.1", "Treino", "Despesa", ""),
            # chave repetida de proposito (ponto 3)
            ("PRJBR4052663500", "PRJBR4052", "663500", "PRIMEIRA", "A", "Custo", ""),
            ("PRJBR4052663500", "PRJBR4052", "663500", "SEGUNDA", "B", "Despesa", ""),
        ],
    )


def _entrada(linhas):
    return pd.DataFrame(linhas, columns=pipeline.COLUNAS_ENTRADA)


# --- Ponto 1: normalizacao de tipo na chave ---------------------------------


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        (140050.0, "140050"),          # float do Excel, sem sufixo .0
        (140050, "140050"),
        ("140050", "140050"),
        ("140050.0", "140050"),        # texto que era numero
        (" 140050 ", "140050"),        # espacos das celulas do SAP
        ("1.234.567", "1234567"),      # separador de milhar
        ("00123", "00123"),            # zeros a esquerda preservados
        ("PRJBR4052", "PRJBR4052"),    # texto nao numerico intacto
        (None, ""),
        (float("nan"), ""),
        ("", ""),
    ],
)
def test_canonizar_normaliza_os_dois_lados(bruto, esperado):
    assert canonizar(bruto) == esperado


def test_conta_numerica_e_textual_dao_a_mesma_chave(mestras):
    """O defeito raiz: no Excel estes dois lados nunca se encontravam."""
    assert montar_chave("PRJBR4052", 140050.0) == montar_chave("PRJBR4052", "140050")
    assert regras.ng("PRJBR4052", 140050.0, mestras) == "1.1.2"
    assert regras.ng("PRJBR4052", "140050", mestras) == "1.1.2"


def test_gl_description_encontra_conta_gravada_como_numero(mestras):
    """Coluna I falhava em 100% das linhas por causa disto."""
    assert regras.gl_description(140050.0, mestras) == "Other Receivables"
    assert regras.gl_description("140050", mestras) == "Other Receivables"
    assert regras.gl_description(999999, mestras) == ""


# --- Ponto 2: centro de custo vazio e caso valido ---------------------------


@pytest.mark.parametrize("vazio", [None, "", "   ", float("nan")])
def test_centro_custo_vazio_correlaciona_pela_conta(mestras, vazio):
    assert montar_chave(vazio, "140050") == "140050"
    assert regras.ng(vazio, "140050", mestras) == "1.1.9"
    assert regras.descricao_ng(vazio, "140050", mestras) == "Recebiveis s/ CC"


def test_centro_custo_vazio_sem_cadastro_vai_para_a_fila_certa(mestras):
    assert regras.ng(None, "663500", mestras) == regras.VALIDACAO
    assert regras.motivo_validacao(None, "663500") == regras.MOTIVO_CC_VAZIO


# --- Ponto 3: chaves duplicadas na tabela mestra ----------------------------


def test_chave_duplicada_usa_primeira_ocorrencia_e_fica_visivel(mestras):
    assert regras.ng("PRJBR4052", "663500", mestras) == "PRIMEIRA"
    duplicadas = mestras.chaves_duplicadas
    assert set(duplicadas["Chave"]) == {"PRJBR4052663500"}
    assert len(duplicadas) == 2  # ambas as linhas ficam registadas, nao so a vencedora


# --- Ponto 4: classificacao vazia significa Base Contabil -------------------


def test_classificacao_vazia_vira_base_contabil(mestras):
    """No Excel o PROCV devolvia 0; aqui '' e None sao casos distintos."""
    assert mestras.classificacao("140050") == ""
    assert regras.validacao(100.0, "140050", mestras) == regras.BASE_CONTABIL


def test_conta_ausente_na_base_gl_vira_validacao(mestras):
    assert mestras.classificacao("999999") is None
    assert regras.validacao(100.0, "999999", mestras) == regras.VALIDACAO


def test_classificacao_preenchida_passa_intacta(mestras):
    assert regras.validacao(100.0, "663500", mestras) == "Analisar"
    assert regras.validacao(100.0, "110028", mestras) == "Exclusão"


# --- Ponto 5: vocabulario fechado de Custo / Despesa Adm --------------------


@pytest.mark.parametrize(
    "variacao", ["Património", "Patrimonio", "patrimonio", "PATRIMONIO", " Patrimônio "]
)
def test_variacoes_de_patrimonio_colapsam(variacao):
    assert normalizar_custo_despesa(variacao) == "Património"


@pytest.mark.parametrize("variacao", ["Receita", "receita", "RECEITA"])
def test_variacoes_de_receita_colapsam(variacao):
    assert normalizar_custo_despesa(variacao) == "Receita"


def test_termos_canonicos_estao_fixados_ate_ao_acento():
    """
    Trava a grafia exata dos termos canonicos.

    A grafia nao e estilo: 'Patrimonio' com acento agudo e a forma usada na
    tabela mestra, e trocar por outra muda a saida de mais de mil linhas de uma
    vez. Ja aconteceu de o acento se perder numa reescrita do ficheiro, por
    isso o teste compara por codepoint em vez de por literal.
    """
    from src.correlacao.vocabulario import TERMOS

    assert TERMOS == (
        "Custo",
        "Despesa",
        "Despesa Financeira",
        "Património",  # o acuto, como na 'Base De-Para'
        "Receita",
    )


def test_vocabulario_recusa_termo_desconhecido():
    with pytest.raises(ValueError, match="Rotulo desconhecido"):
        normalizar_custo_despesa("Investimento")


def test_vocabulario_aceita_vazio():
    assert normalizar_custo_despesa(None) == ""
    assert normalizar_custo_despesa("") == ""


# --- Ponto 6: sem delimitacao por intervalo fixo de linhas ------------------


def test_todas_as_linhas_recebidas_sao_processadas(mestras):
    """As 38 linhas alem do intervalo de formulas nao podem sumir."""
    n = 6834
    entrada = _entrada(
        [("140050", 0.0, i, None, "t", "PRJBR4052", None) for i in range(n)]
    )
    resultado = pipeline.executar(entrada, mestras)
    assert resultado.resumo["linhas_entrada"] == n
    total = len(resultado.correlacionadas) + len(resultado.validacao)
    assert total == n


# --- Ponto 7: coluna N e inerte ---------------------------------------------


def test_conciliacao_devolve_N_quando_a_origem_esta_vazia(mestras):
    """A origem esta vazia em ~todas as linhas: a coluna sai constante."""
    assert regras.conciliacao("PRJBR4052", "140050", mestras) == regras.SEM_CONCILIACAO
    assert regras.conciliacao("INEXISTENTE", "999", mestras) == regras.SEM_CONCILIACAO


def test_conciliacao_devolve_o_valor_quando_a_origem_e_preenchida():
    m = _mestras(
        [("140050", "Other", "")],
        [("140050", "", "140050", "1.1.9", "d", "Despesa", "S")],
    )
    assert regras.conciliacao("", "140050", m) == "S"


# --- Precedencias das colunas L e M -----------------------------------------


def test_wbs_br01471_vence_o_lookup(mestras):
    # a chave existe e diria 'Custo'...
    assert regras.custo_despesa_adm(None, "PRJBR4052", "140050", mestras) == "Custo"
    # ...mas o WBS manda.
    assert (
        regras.custo_despesa_adm("BR01471-BRA1-001", "PRJBR4052", "140050", mestras)
        == regras.DESPESA
    )
    # e vence mesmo sem chave cadastrada.
    assert (
        regras.custo_despesa_adm("BR01471-X", "NAO-EXISTE", "999999", mestras)
        == regras.DESPESA
    )


def test_amount_zero_vence_a_classificacao(mestras):
    assert regras.validacao(0, "663500", mestras) == regras.EXCLUSAO
    assert regras.validacao(0.0, "999999", mestras) == regras.EXCLUSAO
    assert regras.validacao(-0.0, "140050", mestras) == regras.EXCLUSAO


# --- Motivos da fila de validacao -------------------------------------------


@pytest.mark.parametrize(
    "cost_center, esperado",
    [
        (None, regras.MOTIVO_CC_VAZIO),
        ("", regras.MOTIVO_CC_VAZIO),
        ("PRJBRBRA1", regras.MOTIVO_PRJBRBRA1),
        ("PRJBRBRA1C", regras.MOTIVO_COMBINACAO),  # tem sufixo: causa e outra
        ("PRJBR9999", regras.MOTIVO_COMBINACAO),
    ],
)
def test_motivo_validacao(cost_center, esperado):
    assert regras.motivo_validacao(cost_center, "999999") == esperado


# --- Controlos obrigatorios --------------------------------------------------


@pytest.fixture
def entrada_mista():
    return _entrada(
        [
            ("140050", 100.0, 1, None, "a", "PRJBR4052", None),   # correlaciona
            (140050.0, -100.0, 2, None, "b", None, None),          # correlaciona (CC vazio)
            ("999999", 50.0, 3, None, "c", "PRJBRBRA1", None),     # validacao/prjbrbra1
            ("999999", -50.0, 4, None, "d", None, None),           # validacao/cc vazio
            ("663500", 0.0, 5, None, "e", "PRJBR9999", None),      # validacao/combinacao
        ]
    )


def test_conservacao_de_linhas_e_de_valor(entrada_mista, mestras):
    r = pipeline.executar(entrada_mista, mestras)
    assert len(r.correlacionadas) + len(r.validacao) == len(entrada_mista)
    assert r.resumo["soma_saidas"] == pytest.approx(r.resumo["soma_entrada"])


def test_fechamento_em_zero_e_detectado(entrada_mista, mestras):
    r = pipeline.executar(entrada_mista, mestras)
    assert r.resumo["fechamento_em_zero"] is True

    desequilibrada = entrada_mista.copy()
    desequilibrada.loc[0, pipeline.COLUNA_AMOUNT] = 999.0
    r2 = pipeline.executar(desequilibrada, mestras)
    assert r2.resumo["fechamento_em_zero"] is False  # avisa, mas nao aborta


def test_conservacao_falha_alto_quando_violada(entrada_mista, mestras):
    r = pipeline.executar(entrada_mista, mestras)
    with pytest.raises(pipeline.FalhaDeControle, match="Conservacao de linhas"):
        pipeline.verificar_controles(
            entrada_mista, r.correlacionadas.iloc[:0], r.validacao
        )


def test_corte_e_pela_coluna_J_nao_pela_M(entrada_mista, mestras):
    """
    Linha 1: NG encontrado mas M == 'Validacao' (conta fora da 'Base GL')?
    Aqui a linha 0 tem NG e M='Base Contabil'; construimos o caso cruzado.
    """
    m = _mestras(
        gl_linhas=[("111", "so na GL", "Analisar")],
        dp_linhas=[("222", "", "222", "9.9", "so na De-Para", "Custo", "")],
    )
    entrada = _entrada(
        [
            ("222", 10.0, 1, None, "so de-para", None, None),
            ("111", -10.0, 2, None, "so gl", None, None),
        ]
    )
    r = pipeline.executar(entrada, m)
    # conta 222: NG ok -> correlacionadas, mesmo com M == 'Validacao'
    assert list(r.correlacionadas["Account"]) == ["222"]
    assert list(r.correlacionadas["Validação"]) == [regras.VALIDACAO]
    # conta 111: NG ausente -> validacao, mesmo com M preenchido
    assert list(r.validacao["Account"]) == ["111"]
    assert list(r.validacao["Validação"]) == ["Analisar"]


def test_layout_das_saidas(entrada_mista, mestras):
    r = pipeline.executar(entrada_mista, mestras)
    assert list(r.correlacionadas.columns) == pipeline.COLUNAS_SAIDA
    assert list(r.validacao.columns) == pipeline.COLUNAS_SAIDA + ["motivo"]
    assert "Exclusão por Tr" not in r.correlacionadas.columns  # coluna O fica de fora


def test_coluna_ausente_na_exportacao_falha_alto(mestras):
    with pytest.raises(pipeline.FalhaDeControle, match="Colunas ausentes"):
        pipeline.executar(pd.DataFrame({"Account": ["1"]}), mestras)


def test_renomeacao_do_export_bruto_do_sap(mestras):
    """O SAP escreve 'Amount in Local Currency' e 'WBS Element'."""
    bruto = pd.DataFrame(
        {
            "Document Number": [1],
            "Amount in Local Currency": [10.0],
            "Local Currency": ["BRL"],
            "Profit Center": ["COBRA"],
            "Text": ["t"],
            "Cost Center": ["PRJBR4052"],
            "WBS Element": [None],
            "Account": [140050],
            "Posting Date": [pd.Timestamp("2026-07-31")],
        }
    )
    entrada = pipeline.preparar_entrada(bruto)
    assert list(entrada.columns) == pipeline.COLUNAS_ENTRADA
