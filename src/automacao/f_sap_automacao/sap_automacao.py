import asyncio
import io
import os
import re
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from src.Config import SAP_URL, TEST_MODE, TIMEOUT_DOWNLOAD_MS, TIMEOUT_CONFIRMACAO_MS
from src.datetime_utils.datetime_utils import DateTimeUtils
from src.infra.logger import setup_logger

logger = setup_logger(__name__)

# O dialogo "Enter file name to save" que o SAP abre depois de confirmar a
# exportacao tem o nome do arquivo ja proposto (EXPORT_<data>_<hora>.xlsx) e e
# aceito como esta: o carimbo de data/hora proprio e aplicado ao gravar em disco.
#
# Os popups do WebGUI sao 'webguiPopupWindow<n>' (o numero varia) e os botoes
# nao sao <button>: sao divs com a classe 'lsButton'. Por isso o OK e localizado
# por esse par, e nao por role/nome acessivel.
POPUP_WEBGUI = '[id^="webguiPopupWindow"]'
BOTAO_WEBGUI = "div.lsButton"


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
        botao_confirmar=None,
    ) -> io.BytesIO:
        """
        Trata o dialogo de exportacao ja aberto: opcionalmente preenche o nome
        do arquivo, confirma o dialogo e devolve o .xlsx em memoria (BytesIO).

        'botao_confirmar' e o locator que confirma o dialogo. O nome do botao
        varia com o dialogo: o classico usa "OK" (valor por omissao), enquanto
        o "Export as" da grid de partidas confirma pelo proprio "Export to...".

        O SAP pode ou nao abrir o download numa popup; qualquer aba extra
        aberta pelo download e fechada no fim.
        """
        if nome_arquivo:
            campo_nome = page.get_by_role("textbox", name="File Name", exact=True)
            await campo_nome.click()
            await campo_nome.fill(nome_arquivo)

        if botao_confirmar is None:
            botao_confirmar = page.get_by_role("button", name="OK")

        logger.info(
            f"Manipulando download de '{nome_logico}' "
            f"(ate {TIMEOUT_DOWNLOAD_MS // 1000}s)"
        )
        async with page.expect_download(timeout=TIMEOUT_DOWNLOAD_MS) as download_info:
            await botao_confirmar.click()
            await self._clicar_ok(page)
        download = await download_info.value

        with open(await download.path(), "rb") as f:
            conteudo = f.read()

        # O download pode ter sido servido por uma popup; fecha o que sobrou.
        for aba in list(page.context.pages):
            if aba is not page:
                await aba.close()

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

    @staticmethod
    async def _clicar_ok(page: Page) -> bool:
        """
        Clica o "OK" do dialogo "Enter file name to save".

        No WebGUI esse OK e uma div.lsButton dentro de 'webguiPopupWindow<n>',
        e nao um <button> - nem tem nome acessivel. A estrategia principal usa
        esse par; as restantes ficam como rede de seguranca caso o dialogo mude.
        Devolve True se clicou. Se nada casar, os textos dos elementos
        clicaveis visiveis vao para o log, para corrigir o seletor sem adivinhar.
        """
        candidatos = (
            (
                f"{BOTAO_WEBGUI} 'OK' no popup",
                page.locator(f"{POPUP_WEBGUI} {BOTAO_WEBGUI}").filter(
                    has_text=re.compile(r"^\s*OK\s*$")
                ),
            ),
            (
                f"{BOTAO_WEBGUI} 'OK' na pagina",
                page.locator(BOTAO_WEBGUI).filter(
                    has_text=re.compile(r"^\s*OK\s*$")
                ),
            ),
            ("button 'OK'", page.get_by_role("button", name="OK", exact=True)),
            ("texto 'OK'", page.get_by_text("OK", exact=True)),
        )

        prazo = TIMEOUT_CONFIRMACAO_MS / 1000
        limite = asyncio.get_running_loop().time() + prazo
        while asyncio.get_running_loop().time() < limite:
            for descricao, locator in candidatos:
                try:
                    alvo = locator.first
                    if await alvo.is_visible():
                        logger.info(f"Confirmando a exportacao via {descricao}")
                        await alvo.click()
                        return True
                except Exception:
                    continue
            await asyncio.sleep(0.5)

        try:
            visiveis = await page.locator(
                f"{BOTAO_WEBGUI}:visible, button:visible, a:visible, "
                "[role='button']:visible"
            ).all_inner_texts()
            rotulos = sorted({t.strip() for t in visiveis if t.strip()})
            logger.error(
                f"Nenhum 'OK' encontrado em {prazo:.0f}s. "
                f"Elementos clicaveis visiveis: {rotulos}"
            )
        except Exception as e:
            logger.error(f"Nenhum 'OK' encontrado e falhou o diagnostico: {e}")
        return False

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
