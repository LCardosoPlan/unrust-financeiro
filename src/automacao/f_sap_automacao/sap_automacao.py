import io
import os
from playwright.async_api import Page
from src.Config import SAP_URL, TEST_MODE
from src.datetime_utils.datetime_utils import DateTimeUtils
from src.infra.logger import setup_logger

logger = setup_logger(__name__)


class SapAutomation:
    """
    Base reutilizavel da automacao SAP.

    Contem apenas os passos que servem para qualquer transacao:
      - abrir a transacao pelo campo de codigo
      - exportar o grid atual para Excel e capturar o download em memoria

    Os passos especificos de cada transacao (preenchimento do formulario,
    filtros, abas do relatorio) devem ser implementados em 'run'.
    """

    def __init__(self, transacao: str):
        self.transacao = transacao

    async def abrir_transacao(self, page: Page):
        """Navega para o SAP e executa o codigo da transacao."""
        await page.goto(SAP_URL)
        logger.info(f"Acessando transacao {self.transacao}")
        campo = page.get_by_role("combobox", name="Enter transaction code")
        await campo.click()
        await campo.fill(self.transacao)
        await campo.press("Enter")

    async def exportar_excel(self, page: Page, nome_logico: str) -> io.BytesIO:
        """
        Exporta o grid atualmente exibido para .xlsx e devolve o conteudo
        em memoria (BytesIO). Reutilizavel em qualquer transacao com ALV.
        """
        logger.info(f"Extraindo o relatorio '{nome_logico}'...")

        botao_spreadsheet = page.get_by_role("button", name="Spreadsheet... (Ctrl+Shift+F7)")
        await botao_spreadsheet.wait_for(state="visible", timeout=10000)
        await botao_spreadsheet.click()

        botao_export = page.get_by_role("button", name="Export to...")
        await botao_export.wait_for(state="visible", timeout=10000)
        await botao_export.click()

        nome_arquivo = f"{nome_logico} - {DateTimeUtils.get_current_datetime()}.xlsx"
        campo_nome = page.get_by_role("textbox", name="File Name", exact=True)
        await campo_nome.click()
        await campo_nome.fill(nome_arquivo)

        logger.info(f"Manipulando download de '{nome_logico}'")
        async with page.expect_download() as download_info:
            async with page.expect_popup() as popup_info:
                await page.get_by_role("button", name="OK").click()
            popup = await popup_info.value
        download = await download_info.value

        with open(await download.path(), "rb") as f:
            conteudo = f.read()

        await popup.close()

        em_memoria = io.BytesIO(conteudo)
        em_memoria.name = f"{nome_logico}.xlsx"
        em_memoria.seek(0)

        if TEST_MODE:
            pasta = "arquivos_extraidos"
            os.makedirs(pasta, exist_ok=True)
            with open(os.path.join(pasta, f"{nome_logico}.xlsx"), "wb") as f:
                f.write(em_memoria.getvalue())
            logger.info(f">>> [MODO TESTE] Excel gravado em '{pasta}' <<<")

        return em_memoria

    async def run(self, page: Page):
        """
        Ponto de entrada da automacao.

        TODO: implementar os passos da nova transacao aqui, por exemplo:
            await self.abrir_transacao(page)
            # ... preencher filtros da transacao ...
            # await page.get_by_role("button", name="Execute  Emphasized").click()
            # return await self.exportar_excel(page, "relatorio")
        """
        await self.abrir_transacao(page)
        raise NotImplementedError(
            f"Passos da transacao {self.transacao} ainda nao implementados."
        )
