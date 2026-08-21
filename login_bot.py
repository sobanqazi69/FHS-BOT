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
    "https://www.googleapis.com/auth/drive.file",
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


def mark_account_red(sheet, row_number: int):
    try:
        sheet.format(f"A{row_number}", {
            "backgroundColor": {"red": 0.85, "green": 0.11, "blue": 0.11}
        })
        logger.info(f"Marked row {row_number} red in sheet.")
    except Exception as e:
        logger.error(f"Failed to mark row red: {e}")


def _all_texts():
    """Collect (ctrl, text) pairs from visible Xbox and Microsoft account/Sign in windows."""
    pairs = []
    try:
        for win in Desktop(backend="uia").windows():
            try:
                title = win.window_text().strip().lower()
                if not any(k in title for k in ["xbox", "sign in", "microsoft account"]):
                    continue
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
    """Robustly find and click the 'Let's go' button via UIA text search or green pixel scan."""
    import win32gui, pyautogui
    from pywinauto import Desktop

    # Approach A: UIA search across all visible windows
    try:
        desktop = Desktop(backend="uia")
        for win in desktop.windows():
            try:
                title = win.window_text().strip().lower()
                if any(k in title for k in ["xbox", "welcome", "sign in", ""]):
                    for ctrl in win.descendants():
                        try:
                            txt = ctrl.window_text().strip().lower()
                            if "let" in txt and "go" in txt:
                                try:
                                    ctrl.click_input()
                                except Exception:
                                    r = ctrl.rectangle()
                                    pyautogui.click(r.mid_point().x, r.mid_point().y)
                                logger.info(f"[post-login] Clicked 'Let's go': '{ctrl.window_text().strip()}'")
                                return True
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        pass

    # Approach B: Green button scan inside any Xbox / Welcome back popup window
    xbox_hwnds = []
    def _find(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd).lower()
                if "xbox" in t or "welcome" in t or t == "":
                    r = win32gui.GetWindowRect(hwnd)
                    w, h = r[2] - r[0], r[3] - r[1]
                    if 250 < w < 900 and 250 < h < 900:  # popup size window
                        xbox_hwnds.append(hwnd)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_find, None)
    except Exception:
        pass

    for hwnd in xbox_hwnds:
        try:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]

            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            green_xs, green_ys = [], []
            for sy in range(int(h * 0.70), int(h * 0.95), 3):
                for sx in range(int(w * 0.10), int(w * 0.90), 3):
                    r, g, b = px[sx, sy]
                    if g > 100 and r < 70 and b < 70:
                        green_xs.append(rect[0] + sx)
                        green_ys.append(rect[1] + sy)

            if green_xs and green_ys:
                avg_x = sum(green_xs) // len(green_xs)
                avg_y = sum(green_ys) // len(green_ys)
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(0.1)
                pyautogui.click(avg_x, avg_y)
                logger.info(f"[post-login] Clicked 'Let's go' green button via pixel scan at ({avg_x}, {avg_y}).")
                return True
        except Exception:
            pass

    return False


def _try_keep_current_settings() -> bool:
    """Detect and click 'Keep current settings' button if visible on screen via UIA or green pixel scan."""
    import win32gui, pyautogui
    from pywinauto import Desktop

    # Approach A: UIA search across all visible windows
    try:
        desktop = Desktop(backend="uia")
        for win in desktop.windows():
            try:
                title = win.window_text().strip().lower()
                if any(k in title for k in ["xbox", "confirm", "purchases", ""]):
                    for ctrl in win.descendants():
                        try:
                            txt = ctrl.window_text().strip().lower()
                            if "keep current" in txt or "keep using" in txt:
                                try:
                                    ctrl.click_input()
                                except Exception:
                                    r = ctrl.rectangle()
                                    pyautogui.click(r.mid_point().x, r.mid_point().y)
                                clean_txt = ctrl.window_text().encode('ascii', 'ignore').decode('ascii').strip()
                                logger.info(f"[post-login] Clicked 'Keep current settings': '{clean_txt}'")
                                time.sleep(0.5)
                                return True
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        pass

    # Approach B: Scan main Xbox window for green button on the left (Keep current settings)
    xbox_hwnds = []
    def _find(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd).lower()
                if "xbox" in t:
                    r = win32gui.GetWindowRect(hwnd)
                    w, h = r[2] - r[0], r[3] - r[1]
                    if w > 400 and h > 400:
                        xbox_hwnds.append(hwnd)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_find, None)
    except Exception:
        pass

    for hwnd in xbox_hwnds:
        try:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]

            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            green_xs, green_ys = [], []
            for sy in range(int(h * 0.70), int(h * 0.90), 4):
                for sx in range(int(w * 0.25), int(w * 0.45), 4):
                    r, g, b = px[sx, sy]
                    if g > 100 and r < 70 and b < 70:
                        green_xs.append(rect[0] + sx)
                        green_ys.append(rect[1] + sy)

            if green_xs and green_ys:
                avg_x = sum(green_xs) // len(green_xs)
                avg_y = sum(green_ys) // len(green_ys)
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(0.1)
                pyautogui.click(avg_x, avg_y)
                logger.info(f"[post-login] Clicked 'Keep current settings' green button via pixel scan at ({avg_x}, {avg_y}).")
                time.sleep(0.5)
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


def _capture_xbox_screenshot():
    """Return a BytesIO PNG of the main Xbox window, or None on failure."""
    import io, win32gui

    hwnd = None

    def _find(h, _):
        nonlocal hwnd
        if not win32gui.IsWindowVisible(h):
            return
        title = win32gui.GetWindowText(h)
        if "xbox" in title.lower():
            r = win32gui.GetWindowRect(h)
            w, ht = r[2] - r[0], r[3] - r[1]
            if w > 400 and ht > 400:  # main app only, not small popups
                hwnd = h

    win32gui.EnumWindows(_find, None)
    if hwnd is None:
        logger.warning("Xbox window not found for screenshot.")
        return None

    r = win32gui.GetWindowRect(hwnd)
    x, y, w, h = r[0], r[1], r[2] - r[0], r[3] - r[1]
    img = pyautogui.screenshot(region=(x, y, w, h))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _upload_to_catbox(buf) -> str:
    """Upload PNG bytes to catbox.moe (anonymous, permanent) and return a public URL or None."""
    try:
        import requests as req
        buf.seek(0)
        resp = req.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload", "userhash": ""},
            files={"fileToUpload": ("screenshot.png", buf, "image/png")},
            timeout=30,
        )
        url = resp.text.strip()
        if url.startswith("https://"):
            logger.info(f"Screenshot uploaded: {url}")
            return url
        logger.error(f"Unexpected catbox response: {url}")
    except Exception as e:
        logger.error(f"Screenshot upload failed: {e}")
    return None


def add_screenshot_to_sheet(sheet, row_number: int, credentials_file: str, email: str, folder_id: str = ""):
    buf = _capture_xbox_screenshot()
    if buf is None:
        return

    url = _upload_to_catbox(buf)

    if url is None:
        # Fallback — save locally
        os.makedirs("screenshots", exist_ok=True)
        path = os.path.abspath(f"screenshots/xbox_{row_number}_{email}.png")
        buf.seek(0)
        with open(path, "wb") as fh:
            fh.write(buf.read())
        logger.warning(f"Upload failed — screenshot saved locally: {path}")
        return

    try:
        sheet.update([[f'=IMAGE("{url}")']], f"C{row_number}", value_input_option="USER_ENTERED")
        logger.info(f"Screenshot added to sheet row {row_number} column C.")
    except Exception as e:
        logger.error(f"Failed to write screenshot to sheet: {e}")


def _close_xbox_popups():
    """Close any small Xbox popup windows (Welcome back / Let's go screens) leaving the main app open."""
    import win32gui, win32con

    hwnds = []

    def _find(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == "Xbox":
                hwnds.append(hwnd)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(_find, None)
    except Exception:
        pass

    if len(hwnds) <= 1:
        return

    # Keep the largest window (main app), close all smaller ones
    def _area(hwnd):
        try:
            r = win32gui.GetWindowRect(hwnd)
            return (r[2] - r[0]) * (r[3] - r[1])
        except Exception:
            return 0

    hwnds.sort(key=_area, reverse=True)
    for hwnd in hwnds[1:]:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.info("Closed extra Xbox popup window (Welcome back / Let's go).")
        except Exception:
            pass


def _check_protect_account() -> bool:
    """Return True only when 'protect your account' is visible with no skip option."""
    texts = [txt.lower() for _, txt in _all_texts()]
    has_protect = any("protect your account" in t for t in texts)
    has_skip    = any("skip" in t for t in texts)
    return has_protect and not has_skip


def _check_oops() -> bool:
    for _, txt in _all_texts():
        lower = txt.lower()
        if "something went wrong" in lower or ("oops" in lower and len(txt) < 60):
            return True
    return False


# ── Main post-login loop ───────────────────────────────────────────────────────

def _handle_post_login_pages(email: str, password: str, is_retry: bool = False) -> bool:
    """
    Loop and handle whichever post-login page is currently visible.
    Returns False if an unresolvable page (e.g. 'Protect your account') is detected.
    Returns True on normal completion.
    """
    max_wait   = 120
    interval   = 2
    idle_max   = 4
    idle_count = 0
    deadline   = time.time() + max_wait

    logger.info("[post-login] Entering page-handling loop...")

    while time.time() < deadline:
        # Unresolvable: 'Let's protect your account' with no skip
        if _check_protect_account():
            logger.warning("[post-login] 'Protect your account' page detected — cannot skip.")
            return False

        # Oops check (only on first attempt to avoid infinite recursion)
        if not is_retry and _check_oops():
            logger.warning("[post-login] 'Oops' page detected — Alt+F4 and retrying...")
            pyautogui.hotkey("alt", "f4")
            time.sleep(3)
            _click_web_button(["Sign in"], fallback_key="enter")
            time.sleep(2)
            logger.info(f"[post-login] Retrying credentials for {email}...")
            _do_credentials_flow(email, password)
            return True

        handled = (
            _try_skip_for_now()
            or _try_save_and_continue()
            or _try_keep_current_settings()
            or _try_diagnostic_data()
            or _try_lets_go()
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
                return True
            time.sleep(interval)

    logger.warning("[post-login] Timed out waiting for post-login pages.")
    return True


def _try_use_password_instead(timeout: int = 5) -> bool:
    """Check if 'Use your password instead' link is visible and click it."""
    from pywinauto import Desktop
    start = time.time()
    while time.time() - start < timeout:
        try:
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                try:
                    title = win.window_text().strip().lower()
                    if any(k in title for k in ["sign in", "microsoft account", "xbox", ""]):
                        for ctrl in win.descendants():
                            try:
                                txt = ctrl.window_text().strip()
                                lower = txt.lower()
                                if "use your password" in lower or ("password" in lower and "instead" in lower):
                                    try:
                                        ctrl.click_input()
                                    except Exception:
                                        r = ctrl.rectangle()
                                        pyautogui.click(r.mid_point().x, r.mid_point().y)
                                    logger.info(f"[credentials] Clicked 'Use your password instead': '{txt}'")
                                    return True
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(1)
    return False


# ── Credentials flow (shared by main + retry) ─────────────────────────────────

def _do_credentials_flow(email: str, password: str, is_retry: bool = False) -> bool:
    """Scroll account picker → pick Microsoft account → enter email/password. Returns False if account must be skipped."""
    try:
        win = Desktop(backend="uia").window(title="Sign in")
        win.wait("visible", timeout=15)
        win.set_focus()
        logger.info("Account picker opened.")
    except Exception as e:
        logger.error(f"Account picker not found: {e}")
        return True  # picker missing isn't the protect-account case

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

    # Check for 'Use your password instead' link
    logger.info("Waiting 4s after Next to check for 'Use your password instead' link...")
    time.sleep(4)
    if _try_use_password_instead(timeout=5):
        logger.info("Clicked 'Use your password instead', waiting 3s for password field to appear...")
        time.sleep(3)

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
    ok = _handle_post_login_pages(email, password, is_retry=is_retry)
    if not ok:
        return False

    # Catch pages that appear a few seconds after the loop declares done
    time.sleep(3)
    if _check_protect_account():
        logger.warning("[post-login] Late 'Protect your account' page detected.")
        return False
    _try_diagnostic_data()
    return True


def sign_in_with_credentials(email: str, password: str) -> bool:
    logger.info("Waiting 5s for account picker...")
    time.sleep(5)
    return _do_credentials_flow(email, password, is_retry=False)


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
        _close_xbox_popups()    # close any leftover Xbox popup (Welcome back, Let's go, etc.)
        _try_diagnostic_data()  # close any leftover diagnostic data popup
        signout_xbox_account(wait_seconds=10)
        click_xbox_signin(wait_seconds=10)
        ok = sign_in_with_credentials(email, password)

        if not ok:
            logger.warning(f"Unresolvable page for {email} — screenshotting, marking red, skipping.")
            add_screenshot_to_sheet(sheet, row_num, settings.get("credentials_file", "config/credentials.json"), email, settings.get("screenshot_folder_id", ""))
            mark_account_red(sheet, row_num)
            close_xbox()
            time.sleep(5)
            continue

        # Mark blue and capture screenshot before signing out
        mark_account_blue(sheet, row_num)
        add_screenshot_to_sheet(sheet, row_num, settings.get("credentials_file", "config/credentials.json"), email, settings.get("screenshot_folder_id", ""))

        logger.info("Waiting 3s before signing out...")
        time.sleep(3)
        signout_xbox_account(wait_seconds=0)

        logger.info(f"Done with {email}. Moving to next account...")

    logger.info("All accounts processed.")

    logger.info("Starting main.py...")
    main_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    import subprocess
    result = subprocess.run([sys.executable, main_path])
    sys.exit(result.returncode)


if __name__ == "__main__":
    asyncio.run(run())
