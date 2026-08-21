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
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("logs/safeswap.log")],
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


def mark_account_green(sheet, row_number: int):
    try:
        sheet.format(f"A{row_number}", {
            "backgroundColor": {"red": 0.20, "green": 0.78, "blue": 0.35}
        })
        logger.info(f"Marked row {row_number} green in sheet.")
    except Exception as e:
        logger.error(f"Failed to mark row green: {e}")


def _all_texts():
    """Collect (ctrl, text) pairs from all visible windows except developer/editor windows."""
    pairs = []
    try:
        for win in Desktop(backend="uia").windows():
            try:
                title = win.window_text().strip().lower()
                # Exclude editor and terminal windows to avoid matching code or terminal log text
                if any(ex in title for ex in ["visual studio code", "powershell", "cmd.exe", "windows terminal", "antigravity"]):
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


def dismiss_all_xbox_popups() -> bool:
    """Check and dismiss any post-login or Microsoft account popups currently visible."""
    return (
        _try_skip_for_now()
        or _try_save_and_continue()
        or _try_personalized_ads()
        or _try_lets_go()
        or _try_diagnostic_data()
        or _try_keep_current_settings()
        or _try_personalized_recommendations()
    )



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
                time.sleep(3)  # Wait for page to transition before loop continues
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
    import win32gui, pyautogui, time
    from pywinauto import Desktop

    # Approach A: UIA search across all visible windows
    found = False
    try:
        desktop = Desktop(backend="uia")
        for win in desktop.windows():
            try:
                t = win.window_text().strip().lower()
                if any(k in t for k in ["xbox", "personalized ads", "ads", ""]):
                    for ctrl in win.descendants():
                        try:
                            txt = ctrl.window_text().strip().lower()
                            if "no thanks" in txt or "ads won't be" in txt:
                                try:
                                    ctrl.click_input()
                                except Exception:
                                    r = ctrl.rectangle()
                                    pyautogui.click(r.mid_point().x, r.mid_point().y)
                                logger.info("[post-login] Selected 'No thanks' (personalized ads).")
                                found = True
                                time.sleep(0.5)
                                break
                        except Exception:
                            continue
            except Exception:
                continue
            if found:
                break
    except Exception:
        pass

    if found:
        # Click Continue
        time.sleep(0.5)
        try:
            desktop = Desktop(backend="uia")
            for win in desktop.windows():
                try:
                    for ctrl in win.descendants():
                        try:
                            txt = ctrl.window_text().strip().lower()
                            if txt == "continue":
                                ctrl.click_input()
                                logger.info("[post-login] Clicked Continue (ads page).")
                                time.sleep(0.5)
                                return True
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

        pyautogui.press("enter")
        logger.info("[post-login] Pressed Enter for Continue (ads page).")
        return True

    # Approach B: Coordinate / Popup window scan fallback
    xbox_hwnds = []
    def _find(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd):
                r = win32gui.GetWindowRect(hwnd)
                w, h = r[2] - r[0], r[3] - r[1]
                if 250 < w < 900 and 250 < h < 900:  # popup dialog window
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

            desktop = Desktop(backend="uia").window(handle=hwnd)
            for ctrl in desktop.descendants():
                try:
                    txt = ctrl.window_text().strip().lower()
                    if "personalized ads" in txt or "no thanks" in txt:
                        # Click No thanks radio option
                        click_x = rect[0] + int(w * 0.50)
                        click_y = rect[1] + int(h * 0.55)
                        pyautogui.click(click_x, click_y)
                        logger.info(f"[post-login] Clicked 'No thanks' via coords ({click_x}, {click_y}).")
                        time.sleep(0.5)

                        # Click Continue button
                        cont_x = rect[0] + int(w * 0.75)
                        cont_y = rect[1] + int(h * 0.70)
                        pyautogui.click(cont_x, cont_y)
                        logger.info(f"[post-login] Clicked 'Continue' via coords ({cont_x}, {cont_y}).")
                        pyautogui.press("enter")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

    return False


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


def _upload_to_drive(buf, sheet, email: str) -> str | None:
    """Upload PNG bytes to Google Drive via sheet client auth and return direct view URL."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        buf.seek(0)
        drive = build("drive", "v3", credentials=sheet.client.auth)
        filename = f"xbox_{email}_{int(time.time())}.png"
        media = MediaIoBaseUpload(buf, mimetype="image/png", resumable=False)
        file = drive.files().create(
            body={"name": filename},
            media_body=media,
            fields="id",
        ).execute()
        file_id = file["id"]
        drive.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
        url = f"https://drive.google.com/uc?export=view&id={file_id}"
        logger.info(f"Screenshot uploaded to Google Drive: {url}")
        return url
    except Exception as e:
        logger.error(f"Google Drive screenshot upload failed: {e}")
        return None


def add_screenshot_to_sheet(sheet, row_number: int, credentials_file: str, email: str, folder_id: str = ""):
    buf = _capture_xbox_screenshot()
    if buf is None:
        return
    url = _upload_to_catbox(buf)

    if url is None:
        # Fallback 1 — Google Drive upload
        logger.info("Attempting Google Drive upload fallback...")
        url = _upload_to_drive(buf, sheet, email)

    if url is None:
        # Fallback 2 — Save locally
        os.makedirs("screenshots", exist_ok=True)
        path = os.path.abspath(f"screenshots/xbox_{row_number}_{email}.png")
        buf.seek(0)
        with open(path, "wb") as fh:
            fh.write(buf.read())
        logger.warning(f"Upload failed — screenshot saved locally: {path}")
        return

    try:
        sheet.update(f"C{row_number}", [[f'=IMAGE("{url}")']], value_input_option="USER_ENTERED")
        logger.info(f"Screenshot added to sheet row {row_number} column C.")
    except Exception as e:
        logger.error(f"Failed to write screenshot to sheet: {e}")


def _close_xbox_popups():
    """Close any small Xbox popup windows (Welcome back / Let's go screens) leaving the main app open."""
    import win32gui, win32con

    hwnds = []

    def _find(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == "Xbox":
            hwnds.append(hwnd)

    win32gui.EnumWindows(_find, None)
    if len(hwnds) <= 1:
        return

    # Keep the largest window (main app), close all smaller ones
    def _area(hwnd):
        r = win32gui.GetWindowRect(hwnd)
        return (r[2] - r[0]) * (r[3] - r[1])

    hwnds.sort(key=_area, reverse=True)
    for hwnd in hwnds[1:]:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        logger.info("Closed extra Xbox popup window (Welcome back / Let's go).")


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


def _check_xbox_live_error() -> bool:
    for _, txt in _all_texts():
        lower = txt.lower()
        if "we couldn't sign you in to xbox live" in lower or "0x89235107" in lower:
            return True
    return False


def _click_ok_button() -> bool:
    for ctrl, txt in _all_texts():
        if txt.strip().lower() == "ok":
            try:
                ctrl.click_input()
                logger.info("Clicked OK button on error dialog.")
                return True
            except Exception:
                pass
    pyautogui.press("enter")
    logger.info("Pressed Enter as fallback for OK button.")
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
                return True
            time.sleep(interval)

    logger.warning("[post-login] Timed out waiting for post-login pages.")
    return True


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

    if _check_xbox_live_error():
        logger.warning("[post-login] Xbox Live sign-in error detected before page loop.")
        return False

    ok = _handle_post_login_pages(email, password, is_retry=is_retry)
    if not ok:
        return False

    # Catch pages that appear a few seconds after the loop declares done
    time.sleep(3)
    if _check_xbox_live_error():
        logger.warning("[post-login] Xbox Live sign-in error detected after page loop.")
        return False

    if _check_protect_account():
        logger.warning("[post-login] Late 'Protect your account' page detected.")
        return False
    _try_diagnostic_data()
    return True


def sign_in_with_credentials(email: str, password: str) -> bool:
    logger.info("Waiting 5s for account picker...")
    time.sleep(5)
    return _do_credentials_flow(email, password, is_retry=False)


def handle_compatibility_warning(timeout: int = 60):
    import win32gui
    import pyautogui
    logger.info("Polling for Compatibility Warning window...")
    start = time.time()
    while time.time() - start < timeout:
        found = []
        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd).lower()
            if "compatibility" in title and "warning" in title:
                found.append(hwnd)
        win32gui.EnumWindows(_find, None)
        
        for hwnd in found:
            title = win32gui.GetWindowText(hwnd)
            logger.info(f"Found warning window: '{title}' — bringing to foreground and pressing Enter...")
            try:
                from bot.modules.ui_controller import _force_foreground
                _force_foreground(hwnd)
            except Exception:
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
            time.sleep(0.5)
            pyautogui.press("enter")
            logger.info("Pressed Enter to ignore compatibility warning.")
            return True
            
        time.sleep(0.5)
    logger.info("No compatibility warning window appeared within timeout.")
    return False


def wait_for_forza_and_press_enter(timeout: int = 180, stabilize_secs: int = 5):
    """
    Polls for the Forza game window (not the Xbox app).
    Once it appears and is large/fullscreen, waits stabilize_secs seconds
    then presses Enter to start the game from the splash screen.
    """
    import win32gui
    import pyautogui
    logger.info("Waiting for Forza game window to appear...")
    start = time.time()
    while time.time() - start < timeout:
        forza_hwnds = []

        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if (win32gui.IsWindowVisible(hwnd)
                    and "forza" in title.lower()
                    and "xbox" not in title.lower()):
                forza_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        for hwnd in forza_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            # Only act on the actual game window (large, not a tiny stub)
            if w < 800 or h < 500:
                continue

            logger.info(f"Forza game window detected ({w}x{h}). Waiting {stabilize_secs}s for screen to stabilize...")
            time.sleep(stabilize_secs)

            # Bring the window to foreground and press Enter
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.5)
            pyautogui.press("enter")
            logger.info("Pressed Enter on Forza start screen.")
            return True

        time.sleep(1)

    logger.warning("Forza game window did not appear within timeout.")
    return False


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

        max_attempts = 3
        logged_in = False

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Login attempt {attempt}/{max_attempts} for {email}...")
            open_xbox()
            _close_xbox_popups()    # close any leftover Xbox popup (Welcome back, Let's go, etc.)
            _try_diagnostic_data()  # close any leftover diagnostic data popup
            signout_xbox_account(wait_seconds=10)
            click_xbox_signin(wait_seconds=10)
            ok = sign_in_with_credentials(email, password)

            if _check_xbox_live_error():
                logger.warning("Xbox Live sign-in error (0x89235107 / connection error) detected.")
                _click_ok_button()
                close_xbox()
                if attempt < max_attempts:
                    logger.info("Waiting 10s before restarting login process...")
                    time.sleep(10)
                    continue
                else:
                    break

            if ok:
                logged_in = True
                break
            else:
                logger.warning(f"Login attempt {attempt} failed.")
                close_xbox()
                if attempt < max_attempts:
                    logger.info("Waiting 5s before retrying...")
                    time.sleep(5)
                    continue
                else:
                    break

        if not logged_in:
            logger.warning(f"Failed to log in {email} after {max_attempts} attempts — marking red, skipping.")
            add_screenshot_to_sheet(sheet, row_num, settings.get("credentials_file", "config/credentials.json"), email, settings.get("screenshot_folder_id", ""))
            mark_account_red(sheet, row_num)
            close_xbox()
            time.sleep(5)
            continue

        # Mark blue and capture screenshot before launching the game
        mark_account_blue(sheet, row_num)
        add_screenshot_to_sheet(sheet, row_num, settings.get("credentials_file", "config/credentials.json"), email, settings.get("screenshot_folder_id", ""))

        logger.info("Successfully logged in. Waiting 15 seconds before launching Forza...")
        time.sleep(15)

        # Dismiss any leftover popups before launching Forza (personalized ads, protect account, etc.)
        logger.info("Checking for leftover popups before Forza launch...")
        for _ in range(5):
            handled = (
                _try_skip_for_now()
                or _try_save_and_continue()
                or _try_lets_go()
                or _try_personalized_ads()
                or _try_diagnostic_data()
                or _try_keep_current_settings()
                or _try_personalized_recommendations()
            )
            if not handled:
                break
            time.sleep(1)

        logger.info("Launching Forza...")
        from bot.modules.ui_controller import click_forza, click_play
        click_forza(timeout=30)

        # Dismiss any popups that appeared after clicking Forza
        logger.info("Checking for popups before Play...")
        for _ in range(3):
            _try_skip_for_now()
            _try_save_and_continue()
            _try_lets_go()
            _try_personalized_ads()
            time.sleep(1)

        click_play(timeout=30, popup_handler=dismiss_all_xbox_popups)

        # Handle compatibility warning if it pops up
        handle_compatibility_warning(timeout=60)

        # Wait 60 seconds for the game to fully load then press Enter to start
        logger.info("Waiting 35 seconds for Forza to load before pressing Enter...")
        time.sleep(35)
        import pyautogui as _pag
        _pag.press("enter")
        logger.info("Pressed Enter to start Forza.")

        logger.info("Waiting 15s after pressing Enter...")
        time.sleep(15)

        logger.info("Closing game with Alt+F4...")
        pyautogui.hotkey("alt", "f4")

        logger.info("Waiting 10s after closing game...")
        time.sleep(10)

        logger.info("Closing Xbox...")
        close_xbox()

        logger.info("Opening FH6 SAFE SWAP folder...")
        import subprocess
        subprocess.Popen(["explorer", r"C:\Users\pc\Desktop\FH6 SAFE SWAP"])
        time.sleep(2)

        logger.info("Launching ForzaCryptoTool.exe...")
        subprocess.Popen([r"C:\Users\pc\Desktop\FH6 SAFE SWAP\ForzaCryptoTool.exe"])

        logger.info("Waiting 5s for ForzaCryptoTool to load...")
        time.sleep(5)

        import win32gui, win32con, ctypes

        # Find and maximize the ForzaCryptoTool window
        def _find_forza_tool(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "forzacryptotool" in title.lower():
                    results.append(hwnd)

        hwnds = []
        win32gui.EnumWindows(_find_forza_tool, hwnds)

        if hwnds:
            hwnd = hwnds[0]
            logger.info(f"Found ForzaCryptoTool window: {win32gui.GetWindowText(hwnd)}")

            # Use pywinauto to maximize (more reliable for Electron apps)
            try:
                from pywinauto import Desktop as _Desktop
                tool_win = _Desktop(backend="uia").window(title="ForzaCryptoTool")
                tool_win.wait("visible", timeout=10)
                tool_win.maximize()
                logger.info("Maximized ForzaCryptoTool via pywinauto.")
                time.sleep(1)
                tool_win.set_focus()
                time.sleep(0.5)

                # Click "Save Swap" in the sidebar
                clicked = False
                for ctrl in tool_win.descendants():
                    try:
                        if ctrl.window_text().strip().lower() == "save swap":
                            ctrl.click_input()
                            logger.info("Clicked 'Save Swap' via pywinauto.")
                            clicked = True
                            break
                    except Exception:
                        pass

                if not clicked:
                    # Fallback: coordinate-based click on Save Swap in sidebar
                    rect = win32gui.GetWindowRect(hwnd)
                    x = rect[0] + 88
                    y = rect[1] + 207
                    pyautogui.click(x, y)
                    logger.info(f"Clicked Save Swap via pyautogui coords ({x}, {y}).")

                time.sleep(1)

                # Click first Browse button (Donor save)
                browse_clicked = False
                for ctrl in tool_win.descendants():
                    try:
                        if ctrl.window_text().strip().lower() == "browse":
                            ctrl.click_input()
                            logger.info("Clicked first Browse button (Donor save).")
                            browse_clicked = True
                            break
                    except Exception:
                        pass

                if not browse_clicked:
                    rect = win32gui.GetWindowRect(hwnd)
                    pyautogui.click(rect[0] + 530, rect[1] + 168)
                    logger.info("Clicked first Browse via pyautogui fallback.")

                # Handle the file open dialog — type the path and press Enter
                logger.info("Waiting for file dialog...")
                time.sleep(2)
                donor_path = r"C:\Users\pc\Desktop\FH6 SAFE SWAP\C_ProfileData"
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.2)
                pyautogui.typewrite(donor_path, interval=0.03)
                time.sleep(0.3)
                pyautogui.press("enter")
                logger.info(f"Entered donor path: {donor_path}")

                time.sleep(1)

                # Click second Browse button (Active save)
                browse_count = 0
                for ctrl in tool_win.descendants():
                    try:
                        if ctrl.window_text().strip().lower() == "browse":
                            if browse_count == 1:  # second Browse
                                ctrl.click_input()
                                logger.info("Clicked second Browse button (Active save).")
                                break
                            browse_count += 1
                    except Exception:
                        pass

                # Handle second file open dialog
                logger.info("Waiting for second file dialog...")
                time.sleep(2)
                active_path = r"C:\Users\pc\Desktop\FH6 SAFE SWAP\FH6_Profile_IVs_1782016757\profile_ivs.json"
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.2)
                pyautogui.typewrite(active_path, interval=0.03)
                time.sleep(0.3)
                pyautogui.press("enter")
                logger.info(f"Entered active save path: {active_path}")

                time.sleep(1)

                # Click "Auto-detect Active Save" button
                auto_clicked = False
                for ctrl in tool_win.descendants():
                    try:
                        if "auto-detect" in ctrl.window_text().strip().lower() or "auto detect" in ctrl.window_text().strip().lower():
                            ctrl.click_input()
                            logger.info("Clicked 'Auto-detect Active Save'.")
                            auto_clicked = True
                            break
                    except Exception:
                        pass

                if not auto_clicked:
                    rect = win32gui.GetWindowRect(hwnd)
                    pyautogui.click(rect[0] + 207, rect[1] + 372)
                    logger.info("Clicked Auto-detect Active Save via pyautogui fallback.")

                # Wait for 'Select profile save' dialog and click 'Use selected'
                logger.info("Waiting for 'Select profile save' dialog...")
                time.sleep(3)
                use_selected_clicked = False
                for ctrl in tool_win.descendants():
                    try:
                        if "use selected" in ctrl.window_text().strip().lower():
                            ctrl.click_input()
                            logger.info("Clicked 'Use selected'.")
                            use_selected_clicked = True
                            break
                    except Exception:
                        pass

                if not use_selected_clicked:
                    try:
                        dialog = _Desktop(backend="uia").window(title="Select profile save")
                        dialog.wait("visible", timeout=5)
                        for ctrl in dialog.descendants():
                            try:
                                if "use selected" in ctrl.window_text().strip().lower():
                                    ctrl.click_input()
                                    logger.info("Clicked 'Use selected' via dialog ref.")
                                    use_selected_clicked = True
                                    break
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"Dialog not found, pressing Enter as fallback: {e}")
                        pyautogui.press("enter")

                time.sleep(1)

                # Click "Grab XUID" button
                xuid_clicked = False
                for ctrl in tool_win.descendants():
                    try:
                        if "grab xuid" in ctrl.window_text().strip().lower():
                            ctrl.click_input()
                            logger.info("Clicked 'Grab XUID'.")
                            xuid_clicked = True
                            break
                    except Exception:
                        pass

                if not xuid_clicked:
                    rect = win32gui.GetWindowRect(hwnd)
                    pyautogui.click(rect[0] + 314, rect[1] + 482)
                    logger.info("Clicked Grab XUID via pyautogui fallback.")

                logger.info("Waiting 5s after Grab XUID...")
                time.sleep(5)

                def _check_xuid_success():
                    for ctrl in tool_win.descendants():
                        try:
                            if "xuid grabbed" in ctrl.window_text().strip().lower():
                                return True
                        except Exception:
                            pass
                    return False

                def _click_grab_xuid_again():
                    grabbed = False
                    for ctrl in tool_win.descendants():
                        try:
                            if "grab xuid" in ctrl.window_text().strip().lower():
                                ctrl.click_input()
                                logger.info("Clicked 'Grab XUID' (retry).")
                                grabbed = True
                                break
                        except Exception:
                            pass
                    if not grabbed:
                        rect = win32gui.GetWindowRect(hwnd)
                        pyautogui.click(rect[0] + 314, rect[1] + 482)
                        logger.info("Clicked Grab XUID via pyautogui (retry fallback).")

                def _do_swap_save():
                    swap_clicked = False
                    for ctrl in tool_win.descendants():
                        try:
                            if ctrl.window_text().strip().lower() == "swap save":
                                ctrl.click_input()
                                logger.info("Clicked 'Swap Save'.")
                                swap_clicked = True
                                break
                        except Exception:
                            pass
                    if not swap_clicked:
                        rect = win32gui.GetWindowRect(hwnd)
                        pyautogui.click(rect[0] + 155, rect[1] + 610)
                        logger.info("Clicked Swap Save via pyautogui fallback.")

                    logger.info("Waiting for confirmation popup...")
                    time.sleep(2)
                    yes_clicked = False
                    for ctrl in tool_win.descendants():
                        try:
                            if ctrl.window_text().strip().lower() == "yes":
                                ctrl.click_input()
                                logger.info("Clicked 'Yes' on confirmation popup.")
                                yes_clicked = True
                                break
                        except Exception:
                            pass
                    if not yes_clicked:
                        pyautogui.press("enter")
                        logger.info("Pressed Enter as fallback for Yes.")

                    logger.info("Waiting 40s after Swap Save (swap completing)...")
                    time.sleep(40)

                    # Open Xbox and launch game
                    logger.info("Opening Xbox...")
                    open_xbox()

                    logger.info("Launching Forza...")
                    from bot.modules.ui_controller import click_forza, click_play, click_ignore
                    click_forza(timeout=30)
                    click_play(timeout=30, popup_handler=dismiss_all_xbox_popups)

                    logger.info("Waiting for and clicking ignore warning popup...")
                    click_ignore(wait_seconds=30, timeout=60)

                    logger.info("Waiting 35s after ignore...")
                    time.sleep(35)

                    logger.info("Spamming Enter for 10 seconds...")
                    spam_end = time.time() + 10
                    while time.time() < spam_end:
                        pyautogui.press("enter")
                        time.sleep(0.5)
                    logger.info("Done spamming Enter.")

                    # Wait 1 minute
                    logger.info("Waiting 1 minute after spamming Enter...")
                    time.sleep(60)

                    # Screenshot + mark green
                    add_screenshot_to_sheet(sheet, row_num, settings.get("credentials_file", "config/credentials.json"), email, settings.get("screenshot_folder_id", ""))
                    mark_account_green(sheet, row_num)

                    # Wait 20 seconds after marking green
                    logger.info("Waiting 20 seconds after marking account green...")
                    time.sleep(20)

                    # Close game
                    logger.info("Closing game with Alt+F4...")
                    pyautogui.hotkey("alt", "f4")
                    time.sleep(10)

                    # Close Xbox
                    logger.info("Closing Xbox...")
                    try:
                        close_xbox()
                    except Exception as e:
                        logger.warning(f"close_xbox failed (non-critical): {e}")

                    # Close ForzaCryptoTool and FH6 SAFE SWAP folder
                    logger.info("Closing ForzaCryptoTool and FH6 folder...")
                    import subprocess as _sub
                    _sub.Popen(["taskkill", "/F", "/IM", "ForzaCryptoTool.exe"],
                               stdout=_sub.DEVNULL, stderr=_sub.DEVNULL)
                    time.sleep(1)
                    # Close Explorer windows with FH6 SAFE SWAP in title
                    def _close_fh6_folder(hwnd, _):
                        try:
                            title = win32gui.GetWindowText(hwnd)
                            if "fh6 safe swap" in title.lower():
                                win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                        except Exception:
                            pass
                    win32gui.EnumWindows(_close_fh6_folder, None)

                    # Relaunch Xbox and sign out for next account
                    logger.info("Launching Xbox for next account...")
                    open_xbox()
                    time.sleep(10)
                    logger.info("Signing out for next account...")
                    signout_xbox_account(wait_seconds=5)

                if _check_xuid_success():
                    logger.info("XUID grabbed successfully (green). Proceeding to Swap Save.")
                    _do_swap_save()
                else:
                    logger.warning("XUID grab failed (red text). Waiting 30s before retry...")
                    time.sleep(30)
                    _click_grab_xuid_again()
                    logger.info("Waiting 5s after Grab XUID retry...")
                    time.sleep(5)
                    if _check_xuid_success():
                        logger.info("XUID grabbed on retry (green). Proceeding to Swap Save.")
                        _do_swap_save()
                    else:
                        logger.error("XUID grab failed after retry. Skipping Swap Save.")

            except Exception as e:
                logger.warning(f"pywinauto failed for ForzaCryptoTool automation: {e}")
        else:
            logger.warning("ForzaCryptoTool window not found.")


        logger.info("Done. Stopping.")


    logger.info("All accounts processed.")


if __name__ == "__main__":
    asyncio.run(run())
