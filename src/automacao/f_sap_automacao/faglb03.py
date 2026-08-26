import io
from datetime import date
from playwright.async_api import Page
from src.Config import (
    FAGLB03_LEDGER,
    FAGLB03_CONTA_RAZAO,
    FAGLB03_EMPRESA,
    FAGLB03_EXERCICIO,
)
from src.automacao.f_sap_automacao.sap_automacao import SapAutomation
from src.infra.logger import setup_logger

logger = setup_logger(__name__)


class Faglb03Automation(SapAutomation):
    """
    Automacao da transacao FAGLB03 (G/L Account Balance Display).

    Fluxo:
      1. abre a transacao
      2. preenche Ledger / G/L Account / Company Code / Fiscal Year
      3. executa e exporta o saldo por periodo para Excel em memoria
    """

    def __init__(self):
        super().__init__("FAGLB03")

    async def preencher_selecao(self, page: Page):
        """Preenche a tela de selecao da FAGLB03."""
        exercicio = FAGLB03_EXERCICIO or str(date.today().year)

        campos = [
            ("Ledger", FAGLB03_LEDGER),
            ("G/L Account", FAGLB03_CONTA_RAZAO),
            ("Company Code", FAGLB03_EMPRESA),
            ("Fiscal Year", exercicio),
        ]

        logger.info("Preenchendo tela de selecao da FAGLB03")
        for rotulo, valor in campos:
            if not valor:
                logger.info(f"  {rotulo}: (vazio, ignorado)")
                continue
            campo = page.get_by_role("textbox", name=rotulo, exact=True)
            await campo.click()
            await campo.press("ControlOrMeta+a")
            await campo.fill(valor)
            logger.info(f"  {rotulo}: {valor}")

    async def run(self, page: Page) -> io.BytesIO:
        await self.abrir_transacao(page)
        await self.preencher_selecao(page)

        logger.info("Executando o relatorio")
        await page.get_by_role("button", name="Execute  Emphasized").click()

        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            logger.info(f"Aviso: 'networkidle' atingiu o timeout, continuando... - {e}")

        return await self.exportar_excel(page, "faglb03_saldos")
