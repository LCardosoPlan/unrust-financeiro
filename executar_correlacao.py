"""
Executa a etapa de correlacao sobre uma exportacao ja gravada em disco.

Serve para reprocessar um ciclo sem repetir a automacao do SAP. O fluxo online
(main.py) chama o mesmo src.correlacao.pipeline.executar sobre o DataFrame que
ja tem em memoria.

    python executar_correlacao.py "arquivos_extraidos/faglb03_saldos - ....xlsx"
"""

import argparse
import io
from pathlib import Path

from src.correlacao import pipeline, tabelas_mestras
from src.datetime_utils.datetime_utils import DateTimeUtils
from src.infra.logger import setup_logger
from src.processamento_de_dados.planilha_faglb03 import PlanilhaFaglb03

logger = setup_logger(__name__)

XLSB_PADRAO = "Corelação de Contas SAP-NG 2026-Jul.xlsb"
DIRETORIO_SAIDA = Path("saidas")


def gravar(resultado, diretorio: Path, carimbo: str) -> dict:
    """Grava as duas planilhas. Nomes carimbados para nao sobrepor ciclos."""
    diretorio.mkdir(parents=True, exist_ok=True)
    caminhos = {
        "correlacionadas": diretorio / f"correlacionadas - {carimbo}.xlsx",
        "validacao": diretorio / f"validacao - {carimbo}.xlsx",
    }
    resultado.correlacionadas.to_excel(caminhos["correlacionadas"], index=False)
    resultado.validacao.to_excel(caminhos["validacao"], index=False)
    for nome, caminho in caminhos.items():
        logger.info(f"Planilha '{nome}' gravada em {caminho}")
    return caminhos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", help="Caminho do .xlsx exportado do SAP")
    parser.add_argument("--xlsb", default=XLSB_PADRAO, help="Pasta de correlacao")
    parser.add_argument("--saida", default=str(DIRETORIO_SAIDA))
    parser.add_argument(
        "--sem-cache", action="store_true", help="Ignora o cache Parquet das mestras"
    )
    args = parser.parse_args()

    with open(args.export, "rb") as f:
        planilha = PlanilhaFaglb03(io.BytesIO(f.read()), nome_logico="faglb03")
    planilha.registrar_estrutura()

    mestras = tabelas_mestras.carregar(args.xlsb, usar_cache=not args.sem_cache)
    resultado = pipeline.executar(planilha.df, mestras)
    gravar(resultado, Path(args.saida), DateTimeUtils.get_current_datetime())


if __name__ == "__main__":
    main()
