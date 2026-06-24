import logging
from config.settings import Settings
from bot.modules.email_reader import EmailReader
from bot.modules.app_launcher import open_xbox
from bot.modules.ui_controller import signout_xbox_account, click_xbox_signin, select_account, close_signin_popups, dismiss_account_popup, click_lets_go, click_forza, click_play, click_ignore, spam_enter_after_altenter, press_enter_low_memory, press_escape_then_9, wait_then_close_forza, close_xbox

logger = logging.getLogger(__name__)


class Bot:
    def __init__(self):
        self.settings = Settings()
        self._setup_logging()
        self.email_reader = EmailReader(
            credentials_file=self.settings.get("credentials_file", "config/credentials.json"),
            spreadsheet_id=self.settings.get("spreadsheet_id"),
        )

    def _setup_logging(self):
        import sys, os
        os.makedirs("logs", exist_ok=True)
        handlers = [logging.FileHandler("logs/bot.log")]
        if sys.stdout:
            handlers.append(logging.StreamHandler())
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=handlers,
        )

    async def start(self):
        import time
        logger.info("Bot starting...")
        self.email_reader.load(
            sheet_name=self.settings.get("sheet_name", "Sheet1"),
            column=self.settings.get("email_column", 1),
        )

        first = True
        while True:
            email = self.email_reader.get_next()
            if not email:
                logger.info("All emails processed. Bot finished.")
                break

            logger.info(f"Processing: {email}")
            open_xbox()
            if not first:
                signout_xbox_account(wait_seconds=10)
            first = False
            click_xbox_signin(wait_seconds=10)
            selected = select_account(email)
            if not selected:
                logger.warning(f"Account selection failed for {email} — closing all windows and retrying once...")
                close_signin_popups()
                close_xbox()
                time.sleep(5)
                open_xbox()
                signout_xbox_account(wait_seconds=10)
                click_xbox_signin(wait_seconds=10)
                selected = select_account(email)
                if not selected:
                    logger.error(f"Account selection failed again for {email} after retry — skipping.")
                    close_signin_popups()
                    close_xbox()
                    time.sleep(5)
                    continue
            dismiss_account_popup(timeout=15)
            signed_in = click_lets_go(timeout=60)
            if not signed_in:
                logger.warning(f"Sign-in failed for {email} — skipping game launch, moving to next account.")
                close_xbox()
                time.sleep(5)
                continue
            time.sleep(5)
            dismiss_account_popup(timeout=10)
            click_forza(timeout=30)
            click_play(timeout=30)
            click_ignore(wait_seconds=10, timeout=60)
            time.sleep(40)
            spam_enter_after_altenter(duration=30)
            press_enter_low_memory(timeout=120)
            press_escape_then_9(timeout=120)
            wait_then_close_forza(wait_minutes=20)
            self.email_reader.mark_last_green()
            close_xbox()
            logger.info("Waiting 5s before next account...")
            time.sleep(5)
