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
    dismiss_all_post_login_popups,
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
    _upload_to_catbox,
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


def mark_account_grey(sheet, row_number: int):
    """Format row background color to Grey in Google Sheet."""
    try:
        sheet.format(f"A{row_number}", {
            "backgroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}
        })
        logger.info(f"Marked row {row_number} grey in sheet.")
    except Exception as e:
        logger.error(f"Failed to mark row grey: {e}")


def take_game_screenshot_and_add_to_sheet(sheet, row_number: int, email: str):
    """Capture full-screen game screenshot, upload to catbox, insert IMAGE formula into Sheet column C."""
    import io, pyautogui
    try:
        logger.info("Taking full-screen game screenshot...")
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        url = _upload_to_catbox(buf)
        if url:
            sheet.update([[f'=IMAGE("{url}")']], f"C{row_number}", value_input_option="USER_ENTERED")
            logger.info(f"Screenshot URL added to sheet row {row_number} column C: {url}")
        else:
            os.makedirs("screenshots", exist_ok=True)
            local_path = os.path.abspath(f"screenshots/{email}_{int(time.time())}.png")
            img.save(local_path)
            logger.warning(f"Failed catbox upload — saved screenshot locally: {local_path}")
    except Exception as e:
        logger.error(f"Failed to capture and upload screenshot: {e}")


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
            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            x_start, x_end = int(w * 0.30), int(w * 0.70)
            y_start, y_end = int(h * 0.50), int(h * 0.85)

            green_xs, green_ys = [], []
            for sy in range(y_start, y_end, 4):
                for sx in range(x_start, x_end, 4):
                    r, g, b = px[sx, sy]
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


def run_crypto_tool_steps():
    """
    1. Open folder 'C:\\Users\\pc\\Desktop\\FH6 SAFE SWAP'
    2. Launch ForzaCryptoTool.exe and maximize
    3. Click 'Save Swap' in left sidebar
    4. Click 'Browse' (under Donor save)
    5. Select file 'C:\\Users\\pc\\Desktop\\FH6 SAFE SWAP\\C_ProfileData'
    6. Click 'Detect' button under Your account section
    7. Click 'Swap save' button
    8. Click 'Yes' on Confirm save swap popup
    9. Wait 10 seconds and close ForzaCryptoTool
    """
    import subprocess
    import win32gui, win32con, pyautogui
    from pywinauto import Desktop as _Desktop

    logger.info("=== STEP 5: OPENING FH6 SAFE SWAP FOLDER & FORZA CRYPTO TOOL ===")
    try:
        subprocess.Popen(["explorer", r"C:\Users\pc\Desktop\FH6 SAFE SWAP"])
        logger.info("Opened FH6 SAFE SWAP folder.")
    except Exception as e:
        logger.warning(f"Failed to open explorer folder: {e}")
    time.sleep(2)

    logger.info("Launching ForzaCryptoTool.exe...")
    try:
        subprocess.Popen([r"C:\Users\pc\Desktop\FH6 SAFE SWAP\ForzaCryptoTool.exe"])
        logger.info("Launched ForzaCryptoTool.exe.")
    except Exception as e:
        logger.error(f"Failed to launch ForzaCryptoTool.exe: {e}")
        return

    logger.info("Waiting 6s for ForzaCryptoTool to load...")
    time.sleep(6)

    tool_hwnd = None
    def _find_tool(hwnd, _):
        nonlocal tool_hwnd
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if "forzacryptotool" in title or "forza crypto" in title:
                    tool_hwnd = hwnd
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_find_tool, None)
    except Exception:
        pass

    if not tool_hwnd:
        logger.error("ForzaCryptoTool window not found.")
        return

    logger.info(f"Found ForzaCryptoTool window handle: {tool_hwnd}")

    try:
        tool_win = _Desktop(backend="uia").window(handle=tool_hwnd)
        tool_win.wait("visible", timeout=10)
        tool_win.maximize()
        time.sleep(1)
        tool_win.set_focus()
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"Could not maximize via pywinauto: {e}")
        win32gui.ShowWindow(tool_hwnd, win32con.SW_SHOWMAXIMIZED)
        time.sleep(1)

    # Step: Click "Save Swap" on left sidebar
    logger.info("Clicking 'Save Swap' on left sidebar...")
    rect = win32gui.GetWindowRect(tool_hwnd)
    x = rect[0] + 88
    y = rect[1] + 207
    pyautogui.click(x, y)
    logger.info(f"Clicked 'Save Swap' at sidebar coordinates ({x}, {y}).")
    time.sleep(1)

    try:
        tool_win = _Desktop(backend="uia").window(handle=tool_hwnd)
        for ctrl in tool_win.descendants():
            try:
                if ctrl.window_text().strip().lower() == "save swap":
                    ctrl.click_input()
                    logger.info("Clicked 'Save Swap' via UIA button.")
                    break
            except Exception:
                continue
    except Exception:
        pass

    time.sleep(2)

    # Step: Click "Browse" button (under Donor save)
    logger.info("Clicking 'Browse' button...")
    browse_clicked = False
    try:
        tool_win = _Desktop(backend="uia").window(handle=tool_hwnd)
        for ctrl in tool_win.descendants():
            try:
                if ctrl.window_text().strip().lower() == "browse":
                    ctrl.click_input()
                    logger.info("Clicked 'Browse' button via UIA.")
                    browse_clicked = True
                    break
            except Exception:
                continue
    except Exception:
        pass

    if not browse_clicked:
        rect = win32gui.GetWindowRect(tool_hwnd)
        pyautogui.click(rect[0] + 880, rect[1] + 450)
        logger.info("Clicked 'Browse' via coordinate fallback.")

    # Step: Enter donor save file path into file open dialog
    logger.info("Waiting 3s for file dialog...")
    time.sleep(3)
    donor_path = r"C:\Users\pc\Desktop\FH6 SAFE SWAP\C_ProfileData"
    logger.info(f"Selecting donor path in file dialog: {donor_path}")
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.typewrite(donor_path, interval=0.03)
    time.sleep(0.4)
    pyautogui.press("enter")
    logger.info("Entered file path and pressed Enter.")
    time.sleep(2)

    # Step: Click "Detect" button under "Your account" section
    logger.info("Locating 'Detect' button...")
    detect_clicked = False
    try:
        tool_win = _Desktop(backend="uia").window(handle=tool_hwnd)
        for ctrl in tool_win.descendants():
            try:
                txt = ctrl.window_text().strip().lower()
                if txt == "detect" or "detect" in txt:
                    ctrl.click_input()
                    logger.info(f"Clicked 'Detect' button via UIA: '{ctrl.window_text().strip()}'")
                    detect_clicked = True
                    break
            except Exception:
                continue
    except Exception:
        pass

    if not detect_clicked:
        rect = win32gui.GetWindowRect(tool_hwnd)
        click_x = rect[0] + int((rect[2] - rect[0]) * 0.88)
        click_y = rect[1] + int((rect[3] - rect[1]) * 0.67)
        pyautogui.click(click_x, click_y)
        logger.info(f"Clicked 'Detect' button via coordinate fallback ({click_x}, {click_y}).")

    logger.info("Waiting 5 seconds after Detect...")
    time.sleep(5)

    # Step: Click "Swap save" button at bottom of CryptoTool screen
    logger.info("Clicking 'Swap save' button...")
    swap_clicked = False
    try:
        tool_win = _Desktop(backend="uia").window(handle=tool_hwnd)
        for ctrl in tool_win.descendants():
            try:
                txt = ctrl.window_text().strip().lower()
                if txt == "swap save" or "swap save" in txt:
                    ctrl.click_input()
                    logger.info("Clicked 'Swap save' button via UIA.")
                    swap_clicked = True
                    break
            except Exception:
                continue
    except Exception:
        pass

    if not swap_clicked:
        rect = win32gui.GetWindowRect(tool_hwnd)
        click_x = rect[0] + int((rect[2] - rect[0]) * 0.25)
        click_y = rect[1] + int((rect[3] - rect[1]) * 0.86)
        pyautogui.click(click_x, click_y)
        logger.info(f"Clicked 'Swap save' via coordinate fallback ({click_x}, {click_y}).")

    time.sleep(2)

    # Step: Click "Yes" on Confirm save swap popup
    logger.info("Handling 'Confirm save swap' popup...")
    time.sleep(2)
    yes_clicked = False

    popup_hwnds = []
    def _find_popup(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if "confirm" in title or "swap" in title:
                    popup_hwnds.append(hwnd)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_find_popup, None)
    except Exception:
        pass

    if popup_hwnds:
        hwnd = popup_hwnds[0]
        logger.info(f"Found 'Confirm save swap' popup window handle: {hwnd}")
        try:
            from bot.modules.ui_controller import _force_foreground
            _force_foreground(hwnd)
        except Exception:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        time.sleep(0.5)

        # 1. Try UIA click
        try:
            dlg = _Desktop(backend="uia").window(handle=hwnd)
            for ctrl in dlg.descendants():
                try:
                    if ctrl.window_text().strip().lower() == "yes":
                        ctrl.click_input()
                        logger.info("Clicked 'Yes' via UIA.")
                        yes_clicked = True
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Click coordinates of Yes button
        try:
            r = win32gui.GetWindowRect(hwnd)
            yes_x = r[0] + int((r[2] - r[0]) * 0.57)
            yes_y = r[1] + int((r[3] - r[1]) * 0.82)
            pyautogui.click(yes_x, yes_y)
            logger.info(f"Clicked 'Yes' button via coordinates ({yes_x}, {yes_y}).")
            yes_clicked = True
        except Exception:
            pass

        time.sleep(0.3)
        pyautogui.press("enter")
        logger.info("Pressed Enter on popup dialog.")
    else:
        # Search all windows for Yes button
        try:
            desktop = _Desktop(backend="uia")
            for win in desktop.windows():
                try:
                    t = win.window_text().strip().lower()
                    if "confirm" in t or "swap" in t:
                        for ctrl in win.descendants():
                            if ctrl.window_text().strip().lower() == "yes":
                                ctrl.click_input()
                                logger.info("Clicked 'Yes' on popup via UIA search.")
                                yes_clicked = True
                                break
                except Exception:
                    continue
        except Exception:
            pass

        if not yes_clicked:
            pyautogui.press("enter")
            logger.info("Pressed Enter fallback for 'Yes' on popup.")

    logger.info("Waiting 40 seconds for save swap to complete...")
    time.sleep(40)

    # Close ForzaCryptoTool & extra windows
    close_all_windows()
    logger.info("ForzaCryptoTool steps completed successfully.")


def close_all_windows():
    """Close all extra open windows (Explorer folder windows, ForzaCryptoTool, etc.)."""
    import subprocess
    logger.info("Closing all extra open windows (Explorer, ForzaCryptoTool)...")
    try:
        subprocess.run("taskkill /f /im ForzaCryptoTool.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        # Close all Explorer folder windows cleanly
        cmd = 'powershell -command "(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"'
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    time.sleep(2)


async def run():
    settings = Settings()
    cred_file = settings.get("credentials_file", "config/credentials.json")
    sheet_id = settings.get("spreadsheet_id")
    sheet_name = settings.get("sheet_name", "Sheet1")

    if not sheet_id:
        logger.error("No spreadsheet_id found in config/config.json.")
        return

    logger.info("=== STEP 1: INITIAL LOGOUT ===")
    open_xbox()
    _close_xbox_popups()
    _try_diagnostic_data()
    signout_xbox_account(wait_seconds=5)
    logger.info("Waiting 4s after signout...")
    time.sleep(4)

    logger.info("=== STEP 2: PICKING ACCOUNTS FROM GOOGLE SHEET ===")
    accounts, sheet, row_numbers = load_accounts(
        credentials_file=cred_file,
        spreadsheet_id=sheet_id,
        sheet_name=sheet_name,
    )

    if not accounts:
        logger.error("No accounts found in Google Sheet.")
        return

    for (email, password), row_num in zip(accounts, row_numbers):
        logger.info(f"\n=======================================================")
        logger.info(f"   Processing account row {row_num}: {email}")
        logger.info(f"=======================================================")

        logger.info("=== STEP 3: LOGGING IN ACCOUNT ===")
        open_xbox()
        time.sleep(3)
        _close_xbox_popups()
        click_xbox_signin_robust(timeout=15)
        time.sleep(3)

        signed_in = False
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

        dismiss_all_post_login_popups(timeout=10)
        mark_account_blue(sheet, row_num)
        logger.info(f"Successfully signed in as {email}.")

        logger.info("=== STEP 4: FIRST GAME LAUNCH (INITIAL SYNC) ===")
        click_forza(timeout=30)
        click_play(timeout=30)
        click_ignore(wait_seconds=5, timeout=30)

        logger.info("Spamming Enter for 45 seconds...")
        spam_enter_after_altenter(duration=45)

        logger.info("Closing game...")
        close_game()

        logger.info("Waiting 15 seconds on Xbox app...")
        time.sleep(15)

        logger.info("Closing Xbox app...")
        close_xbox()

        logger.info("=== STEP 5: FORZA CRYPTO TOOL SAVE SWAP ===")
        run_crypto_tool_steps()

        logger.info("Ensuring all extra open windows are closed before re-opening Xbox...")
        close_all_windows()

        logger.info("=== STEP 6: RE-OPEN XBOX & SECOND GAME LAUNCH ===")
        open_xbox()
        time.sleep(3)
        dismiss_all_post_login_popups(timeout=10)
        click_forza(timeout=30)
        click_play(timeout=30)
        click_ignore(wait_seconds=5, timeout=30)

        logger.info("Spamming Enter for 90 seconds...")
        spam_enter_after_altenter(duration=90)

        logger.info("=== STEP 7: SCREENSHOT, SHEET UPDATE (GREY) & CLEANUP ===")
        take_game_screenshot_and_add_to_sheet(sheet, row_num, email)
        mark_account_grey(sheet, row_num)

        logger.info("Closing game...")
        close_game()

        logger.info("Waiting 15 seconds on Xbox app...")
        time.sleep(15)

        logger.info("Logging out of Xbox account...")
        signout_xbox_account(wait_seconds=0)

        logger.info(f"Completed processing account {email}. Moving to next account...\n")
        time.sleep(3)

    logger.info("All accounts in Google Sheet processed successfully!")


if __name__ == "__main__":
    asyncio.run(run())
