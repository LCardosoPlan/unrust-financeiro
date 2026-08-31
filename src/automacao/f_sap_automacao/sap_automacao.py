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
      - preencher intervalos de selecao (campo "de" + campo "to")
      - capturar o download do dialogo de exportacao em memoria

    Os passos especificos de cada transacao (filtros, drill-down, abas do
    relatorio) devem ser implementados em 'run' pela subclasse.
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

    async def preencher_intervalo(
        self,
        page: Page,
        rotulo: str,
        valor_de: str,
        valor_ate: str,
        indice_to: int,
    ):
        """
        Preenche um par de campos de selecao do SAP: o campo nomeado 'rotulo'
        (limite inferior) e o campo "to" correspondente (limite superior).

        Os campos "to" da tela nao tem rotulo proprio, por isso sao
        enderecados por posicao ('indice_to'), na mesma ordem em que aparecem
        na tela de selecao.
        """
        campo_de = page.get_by_role("textbox", name=rotulo, exact=True)
        await campo_de.click()
        await campo_de.press("ControlOrMeta+a")
        await campo_de.fill(valor_de or "")
        await campo_de.press("Tab")
        logger.info(f"  {rotulo} (de): {valor_de or '(vazio)'}")

        campo_ate = page.get_by_role("textbox", name="to").nth(indice_to)
        await campo_ate.click()
        await campo_ate.press("ControlOrMeta+a")
        await campo_ate.fill(valor_ate or "")
        await campo_ate.press("Tab")
        logger.info(f"  {rotulo} (ate): {valor_ate or '(vazio)'}")

    async def capturar_download(
        self,
        page: Page,
        nome_logico: str,
        nome_arquivo: str = None,
    ) -> io.BytesIO:
        """
        Trata o dialogo de exportacao ja aberto: opcionalmente preenche o nome
        do arquivo, confirma com OK e devolve o .xlsx em memoria (BytesIO).

        O dialogo do SAP abre o download numa popup; ela e fechada no fim.
        """
        if nome_arquivo:
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
            caminho = os.path.join(
                pasta, f"{nome_logico} - {DateTimeUtils.get_current_datetime()}.xlsx"
            )
            with open(caminho, "wb") as f:
                f.write(em_memoria.getvalue())
            logger.info(f">>> [MODO TESTE] Excel gravado em '{caminho}' <<<")

        return em_memoria

    async def exportar_excel(self, page: Page, nome_logico: str) -> io.BytesIO:
        """
        Exporta o grid ALV atualmente exibido pelo caminho classico
        (Spreadsheet... -> Export to... -> nome do arquivo -> OK).
        """
        logger.info(f"Extraindo o relatorio '{nome_logico}'...")

        botao_spreadsheet = page.get_by_role(
            "button", name="Spreadsheet... (Ctrl+Shift+F7)"
        )
        await botao_spreadsheet.wait_for(state="visible", timeout=10000)
        await botao_spreadsheet.click()

        botao_export = page.get_by_role("button", name="Export to...")
        await botao_export.wait_for(state="visible", timeout=10000)
        await botao_export.click()

        nome_arquivo = (
            f"{nome_logico} - {DateTimeUtils.get_current_datetime()}.xlsx"
        )
        return await self.capturar_download(page, nome_logico, nome_arquivo)

    async def run(self, page: Page):
        """Ponto de entrada da automacao. Implementado por cada transacao."""
        raise NotImplementedError(
            f"Passos da transacao {self.transacao} ainda nao implementados."
        )
