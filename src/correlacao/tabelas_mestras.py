"""
Carga das tabelas mestras da pasta 'Corelacao de Contas SAP-NG'.

Decisao de carregamento: le-se o .xlsb uma vez com pyxlsb e guarda-se o
resultado ja normalizado em Parquet sob 'dados_mestres/', com um manifesto
(sha256 do .xlsb + contagens) que fica versionado. O projeto nao tem base de
dados, o .xlsb e Dado Confidencial Interno e nao deve ir para o repositorio, e
a normalizacao de tipo e cara para repetir a cada execucao - o cache resolve
os tres, e o manifesto da rastreabilidade de qual ciclo gerou cada saida.
"""

import hashlib
import math
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.correlacao.chaves import canonizar_serie, montar_chave_serie
from src.correlacao.vocabulario import normalizar_custo_despesa
from src.infra.logger import setup_logger

logger = setup_logger(__name__)

DIRETORIO_CACHE = Path("dados_mestres")
MANIFESTO = DIRETORIO_CACHE / "manifesto.json"

ABA_GL = "Base GL"
ABA_DE_PARA = "Base De-Para"

# 'Base GL' col. C nao tem cabecalho na planilha; damos-lhe um nome.
COLUNA_CLASSIFICACAO = "Classificacao"

CLASSIFICACOES_CONHECIDAS = {
    "",
    "Exclusão",
    "Analisar",
    "Exclusão por Tr",
    "Reclassificar",
}


@dataclass
class TabelasMestras:
    """As tabelas mestras ja normalizadas e indexadas por chave canonica."""

    gl: pd.DataFrame  # colunas: SAP, GL Description, Classificacao
    de_para: pd.DataFrame  # colunas: Chave, NG, Descricao NG, Custo/Despesa, Conciliacao
    chaves_duplicadas: pd.DataFrame = field(default_factory=pd.DataFrame)
    origem: dict = field(default_factory=dict)

    def __post_init__(self):
        # Indices de lookup. keep="first" reproduz de proposito o comportamento
        # do PROCV perante chave repetida; a duplicidade fica visivel em
        # self.chaves_duplicadas e no log, em vez de desaparecer em silencio.
        self._gl = self.gl.drop_duplicates(subset="SAP", keep="first").set_index("SAP")
        self._dp = self.de_para.drop_duplicates(subset="Chave", keep="first").set_index(
            "Chave"
        )

    def gl_description(self, conta_canonica: str):
        """Coluna I. Devolve None se a conta nao existir na 'Base GL'."""
        if conta_canonica in self._gl.index:
            return self._gl.at[conta_canonica, "GL Description"]
        return None

    def classificacao(self, conta_canonica: str):
        """
        Coluna M (parte). Devolve None se a conta nao existir na 'Base GL'.

        Atencao: uma conta que existe mas tem a classificacao em branco devolve
        "" - que e diferente de None. No Excel os dois casos ficavam iguais,
        porque o PROCV devolve 0 para celula vazia; aqui separam-se.
        """
        if conta_canonica in self._gl.index:
            return self._gl.at[conta_canonica, COLUNA_CLASSIFICACAO]
        return None

    def linha_de_para(self, chave: str):
        """Colunas J, K, L, N. Devolve None se a chave nao estiver cadastrada."""
        if chave in self._dp.index:
            return self._dp.loc[chave]
        return None


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1048576), b""):
            h.update(bloco)
    return h.hexdigest()


def _texto(valor) -> str:
    """Texto aparado; vazio e NaN (que o pyxlsb devolve como float) viram ""."""
    if valor is None:
        return ""
    if isinstance(valor, float) and math.isnan(valor):
        return ""
    return str(valor).strip()


def _ler_aba_xlsb(caminho: Path, aba: str, n_colunas: int) -> pd.DataFrame:
    """
    Le uma aba do .xlsb em bruto, sem cabecalho, com n_colunas fixas.

    Deliberadamente NAO se delimita por intervalo de linhas: percorre-se a aba
    ate ao fim e descartam-se apenas as linhas totalmente vazias no ambito das
    colunas de interesse. Foi um intervalo fixo que deixou 38 linhas sem
    correlacao e sem aviso na versao Excel.
    """
    from pyxlsb import open_workbook

    linhas = []
    with open_workbook(str(caminho)) as wb:
        with wb.get_sheet(aba) as sh:
            for indice, linha in enumerate(sh.rows()):
                celulas = {c.c: c.v for c in linha}
                valores = [celulas.get(i) for i in range(n_colunas)]
                if indice == 0:
                    continue  # cabecalho
                if all(v is None or v == "" for v in valores):
                    continue
                linhas.append(valores)
    logger.info(f"Aba {aba}: {len(linhas)} linhas lidas do .xlsb")
    return pd.DataFrame(linhas, columns=[f"c{i}" for i in range(n_colunas)])


def carregar_base_gl(caminho: Path) -> pd.DataFrame:
    """'Base GL': A=SAP, B=GL Description, C=classificacao (sem cabecalho)."""
    bruto = _ler_aba_xlsb(caminho, ABA_GL, 3)
    df = pd.DataFrame(
        {
            "SAP": canonizar_serie(bruto["c0"]),
            "GL Description": bruto["c1"].map(_texto),
            COLUNA_CLASSIFICACAO: bruto["c2"].map(_texto),
        }
    )
    df = df[df["SAP"] != ""].reset_index(drop=True)

    desconhecidas = set(df[COLUNA_CLASSIFICACAO]) - CLASSIFICACOES_CONHECIDAS
    if desconhecidas:
        raise ValueError(
            f"Classificacoes nao previstas em {ABA_GL} col. C: {sorted(desconhecidas)}"
        )

    # Contas repetidas na 'Base GL' - a mesma conta gravada uma vez como numero
    # e outra como texto. Onde as linhas repetidas dizem o mesmo, a escolha da
    # primeira e inofensiva; onde divergem, a coluna I ou a M dependem de qual
    # linha vence, e isso precisa de decisao humana. Sao casos diferentes e o
    # log separa-os.
    duplicadas = df[df.duplicated("SAP", keep=False)]
    if not duplicadas.empty:
        divergentes = [
            conta
            for conta, grupo in duplicadas.groupby("SAP")
            if len(grupo.drop_duplicates()) > 1
        ]
        logger.warning(
            f"Aba {ABA_GL}: {duplicadas['SAP'].nunique()} contas repetidas apos "
            f"normalizacao ({len(duplicadas)} linhas). Usada a primeira ocorrencia."
        )
        if divergentes:
            logger.warning(
                f"  ATENCAO: {len(divergentes)} destas contas tem conteudo "
                f"DIVERGENTE entre as repeticoes - {sorted(divergentes)}. "
                "A descricao (col. I) ou a classificacao (col. M) mudam consoante "
                "a linha escolhida; corrija a 'Base GL'."
            )
    return df


def carregar_base_de_para(caminho: Path):
    """
    'Base De-Para'. Devolve (tabela, chaves_duplicadas).

    A coluna 'Chave' da planilha e recalculada a partir de C&D em vez de ser
    lida: na origem ela herda o tipo das celulas e por isso nao e comparavel.
    """
    bruto = _ler_aba_xlsb(caminho, ABA_DE_PARA, 9)
    df = pd.DataFrame(
        {
            "Chave": montar_chave_serie(bruto["c2"], bruto["c3"]),
            "Cost Center": canonizar_serie(bruto["c2"]),
            "SAP": canonizar_serie(bruto["c3"]),
            "NG": bruto["c5"].map(_texto),
            "Descrição NG": bruto["c6"].map(_texto),
            "Custo / Despesa Adm": bruto["c7"].map(normalizar_custo_despesa),
            "Conciliação": bruto["c8"].map(_texto),
        }
    )
    df = df[df["Chave"] != ""].reset_index(drop=True)

    contagem = df["Chave"].value_counts()
    repetidas = contagem[contagem > 1]
    duplicadas = (
        df[df["Chave"].isin(repetidas.index)]
        .sort_values("Chave")
        .reset_index(drop=True)
    )
    if not duplicadas.empty:
        logger.warning(
            f"Aba {ABA_DE_PARA}: {len(repetidas)} chaves duplicadas em "
            f"{len(duplicadas)} linhas ({len(df)} linhas, {df['Chave'].nunique()} "
            "chaves distintas). Sera usada a PRIMEIRA ocorrencia, como o PROCV; "
            "as demais ficam no relatorio de duplicadas e precisam de decisao."
        )
        for chave in list(repetidas.index)[:20]:
            logger.warning(f"  chave duplicada: {chave} ({repetidas[chave]}x)")

    # A coluna 'Conciliacao' e hoje inerte. Mantem-se a regra tal como
    # especificada, mas o log deixa claro que a coluna N da saida nao carrega
    # informacao util neste momento - ninguem deve decidir com base nela.
    preenchidas = int((df["Conciliação"] != "").sum())
    logger.warning(
        f"Aba {ABA_DE_PARA} col. I (Conciliacao): apenas {preenchidas} de "
        f"{len(df)} linhas preenchidas. A coluna N da saida e, na pratica, "
        "inerte - nao a use como criterio ate a origem ser preenchida."
    )
    return df, duplicadas


def carregar(caminho_xlsb, usar_cache: bool = True, gravar_cache: bool = True):
    """
    Carrega as tabelas mestras, do cache Parquet quando o .xlsb nao mudou.

    O cache e invalidado pelo sha256 do .xlsb, nao pela data de modificacao.
    """
    caminho = Path(caminho_xlsb)
    if not caminho.exists():
        raise FileNotFoundError(f"Pasta de correlacao nao encontrada: {caminho}")
    digest = _sha256(caminho)

    gl_cache = DIRETORIO_CACHE / "base_gl.parquet"
    dp_cache = DIRETORIO_CACHE / "base_de_para.parquet"
    dup_cache = DIRETORIO_CACHE / "chaves_duplicadas.parquet"

    if usar_cache and MANIFESTO.exists() and gl_cache.exists() and dp_cache.exists():
        manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
        if manifesto.get("sha256") == digest:
            logger.info(f"Tabelas mestras vindas do cache ({DIRETORIO_CACHE}).")
            return TabelasMestras(
                gl=pd.read_parquet(gl_cache),
                de_para=pd.read_parquet(dp_cache),
                chaves_duplicadas=(
                    pd.read_parquet(dup_cache) if dup_cache.exists() else pd.DataFrame()
                ),
                origem=manifesto,
            )
        logger.info("Cache desatualizado (sha256 diferente). A reler o .xlsb.")

    gl = carregar_base_gl(caminho)
    de_para, duplicadas = carregar_base_de_para(caminho)

    origem = {
        "ficheiro": caminho.name,
        "sha256": digest,
        "linhas_base_gl": len(gl),
        "linhas_base_de_para": len(de_para),
        "chaves_distintas": int(de_para["Chave"].nunique()),
        "chaves_duplicadas": int(duplicadas["Chave"].nunique()) if len(duplicadas) else 0,
    }

    if gravar_cache:
        DIRETORIO_CACHE.mkdir(parents=True, exist_ok=True)
        gl.to_parquet(gl_cache, index=False)
        de_para.to_parquet(dp_cache, index=False)
        duplicadas.to_parquet(dup_cache, index=False)
        MANIFESTO.write_text(
            json.dumps(origem, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"Cache das tabelas mestras gravado em {DIRETORIO_CACHE}.")

    return TabelasMestras(
        gl=gl, de_para=de_para, chaves_duplicadas=duplicadas, origem=origem
    )
