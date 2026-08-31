import os
import asyncio
from playwright.async_api import async_playwright, expect
from src.automacao.f_okta_login.okta_login import OktaAuthenticator
from src.automacao.f_sap_automacao.faglb03 import Faglb03Automation
from src.automacao.f_constantes.CONST import (
    AUTH_JSON_PATH,
    PLAN_APPS_TITLE_PAGE,
    LOGON_TITLE_PAGE,
    SAP_TITLE_PAGE,
)
from src.Config import PLAN_EMAIL, PLAN_SENHA, SAP_URL, BROWSER_MODE, TRANSACAO_SAP
from src.datetime_utils.datetime_utils import DateTimeUtils
from src.infra.logger import setup_logger

logger = setup_logger(__name__)

# Transacoes ja implementadas. Novas transacoes entram aqui.
AUTOMACOES = {
    "FAGLB03": Faglb03Automation,
}


async def main():
    """
    Gerencia o ciclo de vida do Playwright, garante a autenticacao no Okta
    (reaproveitando a sessao salva) e executa a automacao SAP.
    """
    resultado = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=BROWSER_MODE)
        storage_state = AUTH_JSON_PATH if os.path.exists(AUTH_JSON_PATH) else None
        context = await browser.new_context(storage_state=storage_state, locale="pt-BR")
        page = await context.new_page()

        try:
            logger.info(f"Acessando SAP ({SAP_URL})")
            await page.goto(SAP_URL, wait_until="networkidle", timeout=60000)

            page_title = await page.title()
            logger.info(page_title)

            if LOGON_TITLE_PAGE in page_title:
                logger.info("Sessao expirada ou invalida. Executando login no Okta.")
                authenticator = OktaAuthenticator(email=PLAN_EMAIL, senha=PLAN_SENHA)
                await authenticator.okta_login(page)
                await expect(page).to_have_title(PLAN_APPS_TITLE_PAGE, timeout=60000)
                logger.info("Login confirmado! Salvando a nova sessao...")

                await context.storage_state(path=AUTH_JSON_PATH)
                logger.info(f"Sessao salva com sucesso em '{AUTH_JSON_PATH}'")

            elif SAP_TITLE_PAGE in page_title:
                logger.info("Login bem-sucedido utilizando a sessao guardada.")

            else:
                raise Exception(f"Pagina inesperada: {page_title}")

            automacao = AUTOMACOES.get(TRANSACAO_SAP.upper())
            if automacao is None:
                raise Exception(
                    f"Transacao '{TRANSACAO_SAP}' nao implementada. "
                    f"Disponiveis: {', '.join(AUTOMACOES)}"
                )

            logger.info("Iniciando automacao SAP...")
            resultado = await automacao().run(page)
            logger.info("Automacao SAP concluida.")

        except Exception as e:
            logger.error(f"Ocorreu um erro fatal durante a automacao: {e}")
            try:
                error_screenshot = (
                    f"error_screenshot - {DateTimeUtils.get_current_datetime()}.png"
                )
                os.makedirs("logs/screenshots", exist_ok=True)
                await page.screenshot(path=f"logs/screenshots/{error_screenshot}")
                logger.info(f"Screenshot de erro salvo em {error_screenshot}")
            except Exception as erro_screenshot:
                # Nao deixar a falha ao capturar o ecra mascarar o erro original.
                logger.warning(f"Nao foi possivel salvar o screenshot: {erro_screenshot}")

        finally:
            logger.info("Fechando navegador.")
            await browser.close()

    # TODO: tratar 'resultado' (processamento / envio) quando a nova transacao estiver definida.
    return resultado


if __name__ == "__main__":
    if not SAP_URL:
        logger.error("Erro: A variavel SAP_URL nao esta definida em src/Config.py.")
    else:
        asyncio.run(main())
