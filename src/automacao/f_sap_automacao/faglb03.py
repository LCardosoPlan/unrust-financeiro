import io
from playwright.async_api import Page
from src.Config import (
    ACCOUNT_NUMBER_START,
    ACCOUNT_NUMBER_END,
    COMPANY_CODE_START,
    COMPANY_CODE_END,
    FISCAL_YEAR,
    FAGLB03_PERIODO,
    FAGLB03_OFFSET_LINHA_PERIODO,
    FAGLB03_TIMEOUT_PARTIDAS_MS,
    FAGLB03_LAYOUT,
)
from src.automacao.f_sap_automacao.sap_automacao import SapAutomation
from src.datetime_utils.datetime_utils import DateTimeUtils
from src.infra.logger import setup_logger

logger = setup_logger(__name__)

# Atalho do SAP que abre o dialogo de exportacao a partir da grid de partidas
# individuais (equivale a Spreadsheet... na grid de saldos).
ATALHO_EXPORTAR = "Shift+F4"

# Atalho que abre o dialogo "Choose Layout" a partir da grid de partidas.
ATALHO_LAYOUT = "Control+F9"


class Faglb03Automation(SapAutomation):
    """
    Automacao da transacao FAGLB03 (G/L Account Balance Display).

    Fluxo (espelha a gravacao do Playwright codegen):
      1. abre a FAGLB03
      2. preenche os intervalos Account Number e Company Code e o Fiscal Year
         do periodo reportado (sempre o mes anterior)
      3. executa o relatorio
      4. abre o drill-down do saldo do periodo reportado (grid de saldos ->
         grid de partidas)
      4.1. troca o layout da grid de partidas (Ctrl+F9)
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

    @staticmethod
    def _periodo_reportado() -> tuple:
        """
        Resolve (ano_fiscal, periodo) do relatorio: por padrao o mes anterior,
        conforme DateTimeUtils.get_previous_fiscal_period(). FISCAL_YEAR e
        FAGLB03_PERIODO na Config sobrescrevem o calculo automatico.
        """
        ano_calculado, periodo_calculado = DateTimeUtils.get_previous_fiscal_period()
        ano = FISCAL_YEAR or ano_calculado
        periodo = int(FAGLB03_PERIODO) if FAGLB03_PERIODO else periodo_calculado

        if not 1 <= periodo <= 12:
            raise ValueError(
                f"Periodo contabil invalido: {periodo}. Esperado 1..12 "
                "(julho = 1, ..., junho = 12)."
            )
        return (str(ano), periodo)

    @classmethod
    def _linha_do_periodo(cls, periodo: int) -> int:
        """Indice da linha da grid de saldos correspondente ao periodo."""
        return periodo + FAGLB03_OFFSET_LINHA_PERIODO

    async def preencher_selecao(self, page: Page):
        """Preenche a tela de selecao da FAGLB03."""
        exercicio, periodo = self._periodo_reportado()
        logger.info(
            f"Preenchendo tela de selecao da FAGLB03 - periodo reportado: "
            f"{periodo} do ano fiscal {exercicio}"
        )

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
        Abre o drill-down: clica no saldo do periodo reportado e, na grid de
        partidas individuais que se abre, foca a primeira linha.
        """
        _, periodo = self._periodo_reportado()
        linha = self._linha_do_periodo(periodo)

        logger.info(f"Abrindo drill-down do saldo do periodo {periodo} (linha {linha})")
        saldo = self._linha_da_grid(page, linha).get_by_role(
            "textbox", name="Balance", exact=True
        )
        await saldo.wait_for(state="visible", timeout=30000)
        # O SAP abre o drill-down com duplo clique; um clique simples apenas
        # seleciona a linha.
        await saldo.dblclick()

        # O relatorio 'G/L Account Line Item Display' pode demorar bem mais que
        # os 30s padrao quando a faixa de contas e ampla, por isso o timeout e
        # configuravel. A primeira partida e localizada pelo icone "Posted" em
        # qualquer linha da grid (nao por um indice fixo), ja que o numero da
        # primeira linha de dados dessa grid nao e conhecido.
        logger.info(
            f"Aguardando a grid de partidas individuais "
            f"(ate {FAGLB03_TIMEOUT_PARTIDAS_MS // 1000}s)"
        )
        partida = page.get_by_role("img", name="Posted").first
        await partida.wait_for(state="visible", timeout=FAGLB03_TIMEOUT_PARTIDAS_MS)
        return partida

    async def aplicar_layout(self, page: Page, partida):
        """
        Abre o dialogo "Choose Layout" (Ctrl+F9) na grid de partidas e
        seleciona FAGLB03_LAYOUT. Um clique na celula do nome do layout ja
        aplica a selecao - o botao "Adopt" nao e necessario.

        Nao devolve locator: as colunas mudam com o layout, por isso os passos
        seguintes usam o teclado da pagina em vez de uma celula da grid.

        A celula e localizada pelo texto, e nao pelo id: o id completo
        ('grid#C164#318,1#if') carrega o prefixo de controlo gerado a cada
        sessao e o numero da linha muda conforme a lista de layouts.
        """
        if not FAGLB03_LAYOUT:
            logger.info("FAGLB03_LAYOUT vazio: mantendo o layout padrao da grid")
            return

        logger.info(f"Abrindo 'Choose Layout' e selecionando '{FAGLB03_LAYOUT}'")
        await partida.press(ATALHO_LAYOUT)

        opcao = page.get_by_text(FAGLB03_LAYOUT, exact=True).first
        await opcao.wait_for(state="visible", timeout=30000)
        await opcao.click()

        # A confirmacao vem da barra de status. Nao se pode esperar pelo icone
        # "Posted": o layout ME1SAP nao tem coluna de status, logo o locator da
        # partida usado ate aqui deixa de existir depois do recarregamento.
        confirmacao = page.get_by_text("Layout was applied", exact=True)
        await confirmacao.wait_for(
            state="visible", timeout=FAGLB03_TIMEOUT_PARTIDAS_MS
        )
        logger.info(f"Layout '{FAGLB03_LAYOUT}' aplicado")

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
        await self.aplicar_layout(page, partida)

        # O atalho vai pelo teclado da pagina: depois da troca de layout o SAP
        # devolve o foco a grid, e nao existe mais uma celula estavel onde
        # pressionar a tecla.
        logger.info("Extraindo o relatorio 'faglb03_saldos'...")
        await page.keyboard.press(ATALHO_EXPORTAR)

        # O atalho abre o dialogo "Export as", cujo botao de confirmacao e o
        # proprio "Export to..." - nao existe botao "OK" nesse dialogo.
        botao_export = page.get_by_role("button", name="Export to...")
        await botao_export.wait_for(state="visible", timeout=10000)

        # A gravacao nao preenche "File Name": neste dialogo o SAP ja propoe o
        # nome por omissao. O carimbo de data/hora e aplicado ao gravar em
        # disco no MODO TESTE.
        return await self.capturar_download(
            page, "faglb03_saldos", botao_confirmar=botao_export
        )
