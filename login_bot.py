import asyncio
import logging
import time
import os
import sys
import pyautogui
import gspread
from pywinauto import Desktop

from bot.modules.app_launcher import open_xbox
from bot.modules.ui_controller import signout_xbox_account, click_xbox_signin, close_xbox
from config.settings import Settings

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("logs/login_bot.log")],
)
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def load_accounts(credentials_file: str, spreadsheet_id: str, sheet_name: str = "Sheet1"):
    client = gspread.service_account(filename=credentials_file, scopes=SCOPES)
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
    accounts = []
    row_numbers = []
    for i, row in enumerate(sheet.get_all_values(), start=1):
        email    = row[0].strip() if len(row) > 0 else ""
        password = row[1].strip() if len(row) > 1 else ""
        if email:
            accounts.append((email, password))
            row_numbers.append(i)
    logger.info(f"Loaded {len(accounts)} account(s) from sheet.")
    return accounts, sheet, row_numbers


def mark_account_blue(sheet, row_number: int):
    try:
        sheet.format(f"A{row_number}", {
            "backgroundColor": {"red": 0.07, "green": 0.52, "blue": 0.81}
        })
        logger.info(f"Marked row {row_number} blue in sheet.")
    except Exception as e:
        logger.error(f"Failed to mark row blue: {e}")


def _all_texts():
    """Collect (ctrl, text) pairs from all visible windows."""
    pairs = []
    try:
        for win in Desktop(backend="uia").windows():
            try:
                for ctrl in win.descendants():
                    try:
                        txt = ctrl.window_text().strip()
                        if txt:
                            pairs.append((ctrl, txt))
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
    return pairs


def _click_web_button(titles: list, fallback_key: str = "enter"):
    try:
        desktop = Desktop(backend="uia")
        for title in titles:
            try:
                btn = desktop.window(best_match="Xbox").child_window(title=title, control_type="Button")
                btn.click_input()
                return True
            except Exception:
                pass
        for win in desktop.windows():
            for title in titles:
                try:
                    btn = win.child_window(title=title, control_type="Button")
                    btn.click_input()
                    return True
                except Exception:
                    pass
    except Exception:
        pass
    pyautogui.press(fallback_key)
    return False


# ── Individual page detectors (return True if they handled the page) ──────────

def _try_skip_for_now() -> bool:
    for ctrl, txt in _all_texts():
        if "skip for now" in txt.lower() or ("7 days" in txt.lower() and "skip" in txt.lower()):
            try:
                ctrl.click_input()
                logger.info(f"[post-login] Clicked 'Skip for now': '{txt}'")
                return True
            except Exception:
                pass
    return False


def _try_save_and_continue() -> bool:
    for ctrl, txt in _all_texts():
        lower = txt.lower()
        if "save" in lower and "continue" in lower:
            try:
                ctrl.click_input()
                logger.info(f"[post-login] Clicked 'Save & continue': '{txt}'")
                return True
            except Exception:
                pass
    return False


def _try_diagnostic_data() -> bool:
    """Select 'Only required data' then click Continue."""
    pairs = _all_texts()
    for ctrl, txt in pairs:
        if "only required data" in txt.lower():
            try:
                ctrl.click_input()
                logger.info("[post-login] Selected 'Only required data'.")
                time.sleep(0.5)
                # Find and click Continue in the same window
                for c2, t2 in _all_texts():
                    if t2.strip().lower() == "continue":
                        try:
                            c2.click_input()
                            logger.info("[post-login] Clicked Continue (diagnostic).")
                            return True
                        except Exception:
                            pass
                return True  # at least selected the radio
            except Exception:
                pass
    return False


def _try_lets_go() -> bool:
    for ctrl, txt in _all_texts():
        lower = txt.lower()
        if "let" in lower and "go" in lower:
            try:
                ctrl.click_input()
                logger.info(f"[post-login] Clicked 'Let's go': '{txt}'")
                return True
            except Exception:
                pass
    return False


def _try_keep_current_settings() -> bool:
    for ctrl, txt in _all_texts():
        if "keep current" in txt.lower():
            try:
                ctrl.click_input()
                logger.info(f"[post-login] Clicked 'Keep current settings': '{txt}'")
                return True
            except Exception:
                pass
    return False


def _try_personalized_recommendations() -> bool:
    """On the 'Personalized recommendations' page: select Generic suggestions then Continue."""
    pairs = _all_texts()
    # Detect the page
    page_visible = any("personalized recommendations" in txt.lower() for _, txt in pairs)
    if not page_visible:
        return False
    # Click "Generic suggestions" radio
    for ctrl, txt in pairs:
        if "generic suggestions" in txt.lower():
            try:
                ctrl.click_input()
                logger.info("[post-login] Selected 'Generic suggestions'.")
                time.sleep(0.5)
                break
            except Exception:
                pass
    # Click Continue
    for ctrl, txt in pairs:
        if txt.strip().lower() == "continue":
            try:
                ctrl.click_input()
                logger.info("[post-login] Clicked Continue (recommendations page).")
                return True
            except Exception:
                pass
    _click_web_button(["Continue"], fallback_key="enter")
    logger.info("[post-login] Clicked Continue (recommendations fallback).")
    return True


def _try_personalized_ads() -> bool:
    """On the 'Personalized ads' page: select No thanks then Continue."""
    pairs = _all_texts()
    page_visible = any("personalized ads" in txt.lower() for _, txt in pairs)
    if not page_visible:
        return False
    # Click "No thanks" radio
    for ctrl, txt in pairs:
        if "no thanks" in txt.lower():
            try:
                ctrl.click_input()
                logger.info("[post-login] Selected 'No thanks' (personalized ads).")
                time.sleep(0.5)
                break
            except Exception:
                pass
    # Click Continue
    for ctrl, txt in pairs:
        if txt.strip().lower() == "continue":
            try:
                ctrl.click_input()
                logger.info("[post-login] Clicked Continue (ads page).")
                return True
            except Exception:
                pass
    _click_web_button(["Continue"], fallback_key="enter")
    logger.info("[post-login] Clicked Continue (ads fallback).")
    return True


def _check_oops() -> bool:
    for _, txt in _all_texts():
        lower = txt.lower()
        if "something went wrong" in lower or ("oops" in lower and len(txt) < 60):
            return True
    return False


# ── Main post-login loop ───────────────────────────────────────────────────────

def _handle_post_login_pages(email: str, password: str, is_retry: bool = False):
    """
    Loop and handle whichever post-login page is currently visible.
    Pages can appear in any order; some may not appear at all.
    Exits after 4 consecutive checks with no recognisable page.
    """
    max_wait   = 120   # total seconds before giving up
    interval   = 2     # seconds between checks
    idle_max   = 4     # consecutive empty checks before declaring done
    idle_count = 0
    deadline   = time.time() + max_wait

    logger.info("[post-login] Entering page-handling loop...")

    while time.time() < deadline:
        # Oops check (only on first attempt to avoid infinite recursion)
        if not is_retry and _check_oops():
            logger.warning("[post-login] 'Oops' page detected — Alt+F4 and retrying...")
            pyautogui.hotkey("alt", "f4")
            time.sleep(3)
            _click_web_button(["Sign in"], fallback_key="enter")
            time.sleep(2)
            logger.info(f"[post-login] Retrying credentials for {email}...")
            _do_credentials_flow(email, password)
            return

        handled = (
            _try_skip_for_now()
            or _try_save_and_continue()
            or _try_diagnostic_data()
            or _try_lets_go()
            or _try_keep_current_settings()
            or _try_personalized_recommendations()
            or _try_personalized_ads()
        )

        if handled:
            idle_count = 0
            time.sleep(interval)
        else:
            idle_count += 1
            logger.info(f"[post-login] No page found ({idle_count}/{idle_max})...")
            if idle_count >= idle_max:
                logger.info("[post-login] All post-login pages handled.")
                return
            time.sleep(interval)

    logger.warning("[post-login] Timed out waiting for post-login pages.")


# ── Credentials flow (shared by main + retry) ─────────────────────────────────

def _do_credentials_flow(email: str, password: str, is_retry: bool = False):
    """Scroll account picker → pick Microsoft account → enter email/password."""
    try:
        win = Desktop(backend="uia").window(title="Sign in")
        win.wait("visible", timeout=15)
        win.set_focus()
        logger.info("Account picker opened.")
    except Exception as e:
        logger.error(f"Account picker not found: {e}")
        return

    # Scroll to very bottom
    try:
        win.child_window(control_type="List").set_focus()
    except Exception:
        win.set_focus()
    for _ in range(30):
        win.type_keys("{PGDN}")
        time.sleep(0.05)
    win.type_keys("{END}")
    time.sleep(0.5)
    logger.info("Scrolled to bottom of account list.")

    # Click "Email, phone, or Skype" subtitle text
    clicked = False
    for ctrl in win.descendants():
        try:
            txt = ctrl.window_text().strip().lower()
            if "email, phone" in txt or "skype" in txt:
                ctrl.click_input()
                logger.info(f"Clicked: '{ctrl.window_text().strip()}'")
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        for ctrl in win.descendants(control_type="ListItem"):
            try:
                if "microsoft account" in ctrl.window_text().strip().lower():
                    ctrl.click_input()
                    logger.info(f"Clicked ListItem: '{ctrl.window_text().strip()}'")
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        win.type_keys("{END}")
        time.sleep(0.3)
        win.type_keys("{ENTER}")
        logger.info("Fallback: pressed Enter on bottom item.")

    # Click Continue instantly
    time.sleep(0.5)
    try:
        win.child_window(title="Continue", control_type="Button").click_input()
        logger.info("Clicked Continue.")
    except Exception:
        pyautogui.press("enter")
        logger.info("Pressed Enter (Continue fallback).")

    # Email
    logger.info("Waiting 10s for email field...")
    time.sleep(10)
    logger.info(f"Typing email: {email}")
    pyautogui.write(email, interval=0.05)
    _click_web_button(["Next"], fallback_key="enter")
    logger.info("Clicked Next.")

    # Password
    logger.info("Waiting 5s for password field...")
    time.sleep(5)
    logger.info("Typing password...")
    pyautogui.write(password, interval=0.05)
    _click_web_button(["Sign in", "Submit"], fallback_key="enter")
    logger.info("Clicked Sign in.")

    # Post-login pages — dynamic loop
    logger.info("Waiting 5s before checking post-login pages...")
    time.sleep(5)
    _handle_post_login_pages(email, password, is_retry=is_retry)


def sign_in_with_credentials(email: str, password: str):
    logger.info("Waiting 5s for account picker...")
    time.sleep(5)
    _do_credentials_flow(email, password, is_retry=False)


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run():
    settings = Settings()
    accounts, sheet, row_numbers = load_accounts(
        credentials_file=settings.get("credentials_file", "config/credentials.json"),
        spreadsheet_id=settings.get("spreadsheet_id"),
        sheet_name=settings.get("sheet_name", "Sheet1"),
    )

    if not accounts:
        logger.error("No accounts found in sheet.")
        return

    for (email, password), row_num in zip(accounts, row_numbers):
        logger.info(f"Processing: {email}")

        open_xbox()
        signout_xbox_account(wait_seconds=10)
        click_xbox_signin(wait_seconds=10)
        sign_in_with_credentials(email, password)

        # Mark blue in sheet before signing out
        mark_account_blue(sheet, row_num)

        logger.info("Waiting 3s before signing out...")
        time.sleep(3)
        signout_xbox_account(wait_seconds=0)

        logger.info(f"Done with {email}. Moving to next account...")

    logger.info("All accounts processed.")


if __name__ == "__main__":
    asyncio.run(run())
