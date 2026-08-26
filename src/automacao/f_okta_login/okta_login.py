from playwright.async_api import Page
from src.Config import OKTA_URL
from src.automacao.f_constantes.CONST import (
    INPUT_EMAIL,
    INPUT_PASS,
    LOGON,
    LOGON_BUTTON
)
from src.infra.logger import setup_logger
logger = setup_logger(__name__)

class OktaAuthenticator:
    """
    Encapsula o login no Okta.
    obs: Não gerencia o navegador, apenas executa as ações na página.
    """

    def __init__(self, email: str, senha: str):
        self.email = email
        self.senha = senha
        self.OKTA_URL = OKTA_URL
        self.INPUT_EMAIL = INPUT_EMAIL
        self.INPUT_PASS = INPUT_PASS
        self.LOGON = LOGON
        self.LOGON_BUTTON = LOGON_BUTTON

    async def okta_login(self, page: Page):
        """
        Navega para a URL do Okta e preenche as credenciais na página de login.
        """
        logger.info("1. Navegando para a pagina de Login do Okta...")
        await page.goto(self.OKTA_URL)
        logger.info("1.1 Preenchendo e-mail e senha...")
        await page.locator(f"#{self.INPUT_EMAIL}").fill(self.email)
        await page.locator(f"#{self.INPUT_PASS}").fill(self.senha)
        await page.get_by_text("Mantenha-me conectado").click()
        await page.get_by_role("button", name=f"{self.LOGON_BUTTON}").click()

        async def cbx_esta_visivel(locator,timeout):
            try:
                await locator.wait_for(state="visible", timeout=timeout)
                return True
            except:
                return False
            
        cbx_receber_notificacao = page.get_by_role("link", name="Selecione para receber uma")
        if await cbx_esta_visivel(cbx_receber_notificacao, 3000):
            await cbx_receber_notificacao.click()
        else:
            return

