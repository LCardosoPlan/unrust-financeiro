import io

import pandas as pd

from src.infra.logger import setup_logger

logger = setup_logger(__name__)


class PlanilhaSap:
    """
    Guarda em memoria uma planilha exportada do SAP como DataFrame.

    Por agora o objetivo e apenas carregar e manter os dados disponiveis: as
    regras de negocio entram depois, como metodos desta classe ou de uma
    subclasse por transacao.

    Nota deliberada sobre os logs: registram apenas a *estrutura* da planilha
    (dimensoes, nomes de coluna, tipos). Os valores nunca vao para o log, por
    serem dados financeiros da organizacao.
    """

    # Nome de uma coluna que identifica a linha de cabecalho. Cada transacao
    # define a sua na subclasse; sem ancora, cai na heuristica de _detectar.
    COLUNA_ANCORA = None

    # Quantas linhas do topo inspecionar a procura do cabecalho.
    LINHAS_BUSCA_CABECALHO = 30

    def __init__(
        self,
        excel: io.BytesIO,
        nome_logico: str = "planilha",
        linha_cabecalho: int = None,
    ):
        self.nome_logico = nome_logico
        if linha_cabecalho is None:
            linha_cabecalho = self._detectar_cabecalho(excel)
        self.linha_cabecalho = linha_cabecalho
        self.df = self._carregar(excel)

    def _detectar_cabecalho(self, excel: io.BytesIO) -> int:
        """
        Descobre em que linha esta o cabecalho dos dados.

        O export do SAP comeca com um bloco de titulo (G/L Account, Company
        Code, Ledger) e linhas vazias, por isso o cabecalho nao esta na linha 0.
        Um indice fixo seria fragil: bastaria o SAP acrescentar uma linha ao
        bloco. Com COLUNA_ANCORA definida, procura-se a linha que a contem e
        falha-se de forma explicita se ela nao existir - sinal de que o layout
        mudou. Sem ancora, usa-se a linha mais preenchida do topo.
        """
        excel.seek(0)
        topo = pd.read_excel(
            excel, engine="openpyxl", header=None, nrows=self.LINHAS_BUSCA_CABECALHO
        )

        if self.COLUNA_ANCORA:
            alvo = self.COLUNA_ANCORA.strip().casefold()
            for indice in range(len(topo)):
                celulas = {
                    str(v).strip().casefold()
                    for v in topo.iloc[indice].tolist()
                    if pd.notna(v)
                }
                if alvo in celulas:
                    logger.info(
                        f"Cabecalho de '{self.nome_logico}' na linha {indice} "
                        f"(ancora: '{self.COLUNA_ANCORA}')"
                    )
                    return indice
            raise ValueError(
                f"Coluna ancora '{self.COLUNA_ANCORA}' nao encontrada nas "
                f"primeiras {self.LINHAS_BUSCA_CABECALHO} linhas de "
                f"'{self.nome_logico}'. O layout do relatorio pode ter mudado."
            )

        indice = int(topo.notna().sum(axis="columns").idxmax())
        logger.info(
            f"Cabecalho de '{self.nome_logico}' na linha {indice} "
            "(linha mais preenchida do topo; sem coluna ancora definida)"
        )
        return indice

    def _carregar(self, excel: io.BytesIO) -> pd.DataFrame:
        """
        Le o .xlsx em memoria e devolve o DataFrame.

        O BytesIO pode ja ter sido lido antes (por exemplo ao gravar em disco),
        por isso o ponteiro e rebobinado. Os tipos sao os inferidos pelo pandas:
        a conversao de numeros e datas do SAP fica para as regras de negocio,
        quando o formato real das colunas estiver conhecido.
        """
        try:
            excel.seek(0)
            df = pd.read_excel(
                excel, engine="openpyxl", header=self.linha_cabecalho
            )
        except Exception as e:
            logger.error(f"Falha ao ler o Excel de '{self.nome_logico}': {e}")
            raise ValueError(f"Falha ao ler o Excel de '{self.nome_logico}': {e}")

        df.columns = [str(c).strip() for c in df.columns]

        # O export do SAP costuma trazer colunas e linhas totalmente vazias.
        antes = df.shape
        df = df.dropna(axis="columns", how="all").dropna(axis="index", how="all")
        if df.shape != antes:
            logger.info(
                f"Descartadas colunas/linhas vazias: {antes} -> {df.shape}"
            )

        logger.info(
            f"Planilha '{self.nome_logico}' carregada: "
            f"{len(df)} linhas x {len(df.columns)} colunas"
        )
        logger.info(f"  Colunas: {list(df.columns)}")
        return df

    def estrutura(self) -> dict:
        """
        Metadados da planilha, uteis para decidir as proximas transformacoes
        sem expor valores: tipo inferido e contagem de vazios por coluna.
        """
        return {
            "nome_logico": self.nome_logico,
            "linhas": len(self.df),
            "colunas": {
                nome: {
                    "tipo": str(self.df[nome].dtype),
                    "vazios": int(self.df[nome].isna().sum()),
                }
                for nome in self.df.columns
            },
        }

    def registrar_estrutura(self):
        """Envia a estrutura da planilha para o log, coluna por coluna."""
        estrutura = self.estrutura()
        logger.info(
            f"Estrutura de '{self.nome_logico}' ({estrutura['linhas']} linhas):"
        )
        for nome, info in estrutura["colunas"].items():
            logger.info(f"  {nome}: tipo={info['tipo']} vazios={info['vazios']}")

    def __len__(self) -> int:
        return len(self.df)
