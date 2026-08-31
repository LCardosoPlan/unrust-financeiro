from src.Config import FAGLB03_COLUNA_ANCORA
from src.processamento_de_dados.planilha_sap import PlanilhaSap


class PlanilhaFaglb03(PlanilhaSap):
    """
    Planilha de partidas individuais da FAGLB03 no layout ME1SAP.

    Colunas observadas no export: Document Number, Amount in Local Currency,
    Local Currency, Profit Center, Text, Cost Center, WBS Element, Account,
    Posting Date. Os tipos vem prontos do pandas (int64/float64/datetime64),
    inclusive o sinal negativo a direita usado pelo SAP - por isso nao ha
    conversao de tipos aqui.

    As regras de negocio da transacao entram nesta classe.
    """

    COLUNA_ANCORA = FAGLB03_COLUNA_ANCORA
