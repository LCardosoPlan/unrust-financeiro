import io
from playwright.async_api import Page
from src.Config import (
    ACCOUNT_NUMBER_START,
    ACCOUNT_NUMBER_END,
    COMPANY_CODE_START,
    COMPANY_CODE_END,
    FISCAL_YEAR,
    FAGLB03_LINHA_SALDO,
    FAGLB03_LINHA_PARTIDAS,
)
from src.automacao.f_sap_automacao.sap_automacao import SapAutomation
from src.datetime_utils.datetime_utils import DateTimeUtils
from src.infra.logger import setup_logger

logger = setup_logger(__name__)

# Atalho do SAP que abre o dialogo de exportacao a partir da grid de partidas
# individuais (equivale a Spreadsheet... na grid de saldos).
ATALHO_EXPORTAR = "Shift+F4"


class Faglb03Automation(SapAutomation):
    """
    Automacao da transacao FAGLB03 (G/L Account Balance Display).

    Fluxo (espelha a gravacao do Playwright codegen):
      1. abre a FAGLB03
      2. preenche os intervalos Account Number e Company Code e o Fiscal Year
      3. executa o relatorio
      4. abre o drill-down de um saldo (grid de saldos -> grid de partidas)
      5. dispara a exportacao pelo atalho e captura o .xlsx em memoria
    """

    def __init__(self):
        super().__init__("FAGLB03")

    @staticmethod
    def _linha_da_grid(page: Page, indice: int):
        """
        Localiza uma linha de grid do SAP UI5.

        Os ids completos ('C117-mrss-cont-none-Row-2') carregam um prefixo de
        controlo gerado a cada sessao, por isso ancoramos apenas o sufixo
        estavel via seletor CSS.
        """
        return page.locator(f'[id$="-mrss-cont-none-Row-{indice}"]')

    async def preencher_selecao(self, page: Page):
        """Preenche a tela de selecao da FAGLB03."""
        exercicio = FISCAL_YEAR or DateTimeUtils.get_fiscal_year()

        logger.info("Preenchendo tela de selecao da FAGLB03")

        # Os campos "to" nao tem rotulo proprio: indice 0 = Account Number,
        # indice 1 = Company Code, na ordem em que surgem na tela.
        await self.preencher_intervalo(
            page, "Account Number", ACCOUNT_NUMBER_START, ACCOUNT_NUMBER_END, 0
        )
        await self.preencher_intervalo(
            page, "Company Code", COMPANY_CODE_START, COMPANY_CODE_END, 1
        )

        campo_exercicio = page.get_by_role("textbox", name="Fiscal Year", exact=True)
        await campo_exercicio.click()
        await campo_exercicio.press("ControlOrMeta+a")
        await campo_exercicio.fill(exercicio)
        logger.info(f"  Fiscal Year: {exercicio}")

    async def abrir_partidas_individuais(self, page: Page):
        """
        Abre o drill-down: clica no saldo da linha configurada e, na grid de
        partidas individuais que se abre, foca a primeira linha.
        """
        logger.info(f"Abrindo drill-down do saldo (linha {FAGLB03_LINHA_SALDO})")
        saldo = self._linha_da_grid(page, FAGLB03_LINHA_SALDO).get_by_role(
            "textbox", name="Balance", exact=True
        )
        await saldo.wait_for(state="visible", timeout=30000)
        await saldo.click()

        logger.info("Aguardando a grid de partidas individuais")
        partida = self._linha_da_grid(page, FAGLB03_LINHA_PARTIDAS).get_by_role(
            "img", name="Posted"
        )
        await partida.wait_for(state="visible", timeout=30000)
        return partida

    async def run(self, page: Page) -> io.BytesIO:
        await self.abrir_transacao(page)
        await self.preencher_selecao(page)

        logger.info("Executando o relatorio")
        await page.get_by_role("button", name="Execute  Emphasized").click()

        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            logger.info(f"Aviso: 'networkidle' atingiu o timeout, continuando... - {e}")

        partida = await self.abrir_partidas_individuais(page)

        logger.info("Extraindo o relatorio 'faglb03_saldos'...")
        await partida.press(ATALHO_EXPORTAR)

        botao_export = page.get_by_role("button", name="Export to...")
        await botao_export.wait_for(state="visible", timeout=10000)
        await botao_export.click()

        # A gravacao nao preenche "File Name": neste dialogo o SAP ja propoe o
        # nome por omissao. O carimbo de data/hora e aplicado ao gravar em
        # disco no MODO TESTE.
        return await self.capturar_download(page, "faglb03_saldos")
