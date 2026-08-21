import asyncio
import logging
import os
import sys
import time
import gspread

from bot.modules.app_launcher import open_xbox
from bot.modules.ui_controller import (
    signout_xbox_account,
    click_xbox_signin,
    select_account,
    close_signin_popups,
    dismiss_account_popup,
    click_lets_go,
    click_forza,
    click_play,
    click_ignore,
    spam_enter_after_altenter,
    close_xbox,
)
from login_bot import (
    sign_in_with_credentials,
    _close_xbox_popups,
    _try_diagnostic_data,
    mark_account_blue,
    mark_account_red,
)
from config.settings import Settings

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("logs/logout_login_game.log")],
)
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_accounts(credentials_file: str, spreadsheet_id: str, sheet_name: str = "Sheet1"):
    """Load accounts (email, password) and row numbers from Google Sheet."""
    client = gspread.service_account(filename=credentials_file, scopes=SCOPES)
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
    accounts = []
    row_numbers = []
    for i, row in enumerate(sheet.get_all_values(), start=1):
        email = row[0].strip() if len(row) > 0 else ""
        password = row[1].strip() if len(row) > 1 else ""
        if email:
            accounts.append((email, password))
            row_numbers.append(i)
    logger.info(f"Loaded {len(accounts)} account(s) from sheet.")
    return accounts, sheet, row_numbers


def click_xbox_signin_robust(timeout: int = 15) -> bool:
    """Robustly find and click the 'Sign in' button in Xbox app via UIA or pixel scan."""
    import win32gui
    import pyautogui
    from pywinauto import Desktop

    logger.info("Polling to click Xbox 'Sign in' button...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        # 1. Try UIA search across all visible windows
        try:
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                try:
                    title = win.window_text().strip().lower()
                    if "xbox" in title or win.class_name() in ["ApplicationFrameWindow", "Windows.UI.Core.CoreWindow"]:
                        for ctrl in win.descendants(control_type="Button"):
                            if ctrl.window_text().strip().lower() == "sign in":
                                ctrl.click_input()
                                logger.info("Clicked 'Sign in' button via UIA.")
                                return True
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Find Xbox window using win32gui and bring to front
        xbox_hwnds = []
        def _find(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd).lower()
                    if "xbox" in t or "microsoft" in t:
                        xbox_hwnds.append(hwnd)
            except Exception:
                pass
        try:
            win32gui.EnumWindows(_find, None)
        except Exception:
            pass

        if xbox_hwnds:
            hwnd = xbox_hwnds[0]
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.2)
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]

            # 3. Scan for the green 'Sign in' button inside the Xbox window
            # Scanning region: x from 30% to 70%, y from 50% to 85%
            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            x_start, x_end = int(w * 0.30), int(w * 0.70)
            y_start, y_end = int(h * 0.50), int(h * 0.85)

            green_xs, green_ys = [], []
            for sy in range(y_start, y_end, 4):
                for sx in range(x_start, x_end, 4):
                    r, g, b = px[sx, sy]
                    # Microsoft Green: G > 100, R < 70, B < 70
                    if g > 100 and r < 70 and b < 70:
                        green_xs.append(rect[0] + sx)
                        green_ys.append(rect[1] + sy)

            if green_xs and green_ys:
                avg_x = sum(green_xs) // len(green_xs)
                avg_y = sum(green_ys) // len(green_ys)
                pyautogui.click(avg_x, avg_y)
                logger.info(f"Clicked green 'Sign in' button via pixel scan at ({avg_x}, {avg_y}).")
                return True

        time.sleep(1)

    logger.error("Failed to find or click 'Sign in' button within timeout.")
    return False


def close_game():
    """Close Forza game window gracefully using Alt+F4 / taskkill."""
    import win32gui, pyautogui, subprocess
    logger.info("Closing game window...")
    forza_hwnds = []

    def _find(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if "forza" in title and "xbox" not in title:
                    forza_hwnds.append(hwnd)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_find, None)
    except Exception:
        pass

    for hwnd in forza_hwnds:
        try:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            pyautogui.hotkey("alt", "f4")
            logger.info("Sent Alt+F4 to Forza.")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Alt+F4 failed: {e}")

    try:
        subprocess.run("taskkill /f /im ForzaMotorsport.exe /im ForzaHorizon5.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Taskkill fallback executed for Forza.")
    except Exception:
        pass


async def run():
    settings = Settings()
    cred_file = settings.get("credentials_file", "config/credentials.json")
    sheet_id = settings.get("spreadsheet_id")
    sheet_name = settings.get("sheet_name", "Sheet1")

    if not sheet_id:
        logger.error("No spreadsheet_id found in config/config.json.")
        return

    logger.info("=== STEP 1: LOGGING OUT CURRENT XBOX ACCOUNT ===")
    open_xbox()
    _close_xbox_popups()
    _try_diagnostic_data()
    signout_xbox_account(wait_seconds=5)
    logger.info("Waiting 4s after signout...")
    time.sleep(4)

    logger.info("=== STEP 2: PICKING ACCOUNT FROM GOOGLE SHEET ===")
    accounts, sheet, row_numbers = load_accounts(
        credentials_file=cred_file,
        spreadsheet_id=sheet_id,
        sheet_name=sheet_name,
    )

    if not accounts:
        logger.error("No accounts found in Google Sheet.")
        return

    for (email, password), row_num in zip(accounts, row_numbers):
        logger.info(f"\n--- Processing account from sheet row {row_num}: {email} ---")

        logger.info("=== STEP 3: LOGGING IN ACCOUNT ===")
        open_xbox()
        time.sleep(3)
        _close_xbox_popups()
        click_xbox_signin_robust(timeout=15)
        time.sleep(3)

        signed_in = False
        # Try account picker selection first if account is already listed on device
        if select_account(email, wait_seconds=2):
            logger.info(f"Selected account '{email}' via Windows Account Picker.")
            dismiss_account_popup(timeout=15)
            signed_in = click_lets_go(timeout=60)
        else:
            logger.info(f"Account '{email}' not in picker list — performing credentials sign-in flow...")
            signed_in = sign_in_with_credentials(email, password)

        if not signed_in:
            logger.warning(f"Sign-in failed for {email} — marking red and skipping.")
            mark_account_red(sheet, row_num)
            close_xbox()
            time.sleep(3)
            continue

        mark_account_blue(sheet, row_num)
        logger.info(f"Successfully signed in as {email}.")

        logger.info("=== STEP 4: OPENING GAME ===")
        click_forza(timeout=30)
        click_play(timeout=30)
        click_ignore(wait_seconds=5, timeout=30)
        logger.info("Game launch sequence initiated successfully.")

        logger.info("Spamming Enter for 45 seconds...")
        spam_enter_after_altenter(duration=45)

        logger.info("Closing game...")
        close_game()

        logger.info("Waiting 15 seconds on Xbox app...")
        time.sleep(15)

        logger.info("Closing Xbox app...")
        close_xbox()
        break  # Processed the account and completed sequence


if __name__ == "__main__":
    asyncio.run(run())
