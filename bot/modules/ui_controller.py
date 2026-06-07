import time
import logging
import pyautogui
from pywinauto import Desktop

pyautogui.FAILSAFE = False

logger = logging.getLogger(__name__)


def signout_xbox_account(wait_seconds: int = 10):
    import win32gui

    logger.info(f"Waiting {wait_seconds}s then signing out of current Xbox account...")
    time.sleep(wait_seconds)

    xbox_hwnds = []

    def _find(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and "xbox" in win32gui.GetWindowText(hwnd).lower():
            xbox_hwnds.append(hwnd)

    win32gui.EnumWindows(_find, None)

    for hwnd in xbox_hwnds:
        rect = win32gui.GetWindowRect(hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w < 200 or h < 200:
            continue

        try:
            _force_foreground(hwnd)
        except Exception:
            pass
        time.sleep(0.3)

        # Click profile/ULTIMATE icon at top-left of Xbox sidebar
        profile_x = rect[0] + int(w * 0.04)
        profile_y = rect[1] + int(h * 0.05)

        def _try_signout():
            pyautogui.click(profile_x, profile_y)
            logger.info(f"Clicked profile icon at ({profile_x}, {profile_y}).")
            time.sleep(1.5)

            # UIA search for Sign out
            try:
                from pywinauto import Desktop as _Desktop
                xbox_win = _Desktop(backend="uia").window(handle=hwnd)
                for ctrl in xbox_win.descendants():
                    try:
                        if ctrl.window_text().strip().lower() == "sign out":
                            ctrl.click_input()
                            logger.info("Clicked Sign out via UIA.")
                            time.sleep(2)
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

            # Pixel fallback: Sign out is ~78% down the dropdown on the left side
            so_x = rect[0] + int(w * 0.08)
            so_y = rect[1] + int(h * 0.78)
            pyautogui.click(so_x, so_y)
            logger.info(f"Clicked Sign out at fallback pixel ({so_x}, {so_y}).")
            time.sleep(2)
            return False

        # Try once, retry if UIA didn't confirm it
        found = _try_signout()
        if not found:
            logger.warning("Sign out not confirmed via UIA — retrying once...")
            _try_signout()
        return

    logger.warning("Xbox window not found for sign-out.")


def click_xbox_signin(wait_seconds: int = 5):
    logger.info(f"Waiting {wait_seconds}s for Xbox to load...")
    time.sleep(wait_seconds)

    try:
        desktop = Desktop(backend="uia")
        xbox_win = desktop.window(title_re=".*Xbox.*")
        xbox_win.wait("visible", timeout=15)
        logger.info("Xbox window found.")

        signin_btn = xbox_win.child_window(title="Sign in", control_type="Button")
        signin_btn.click_input()
        logger.info("Clicked 'Sign in' button.")
    except Exception as e:
        logger.error(f"Failed to click Sign in button: {e}")


def select_account(email: str, wait_seconds: int = 3):
    logger.info(f"Searching for account: {email}")
    time.sleep(wait_seconds)

    try:
        desktop = Desktop(backend="uia")
        win = desktop.window(title="Sign in")
        win.wait("visible", timeout=10)
        win.set_focus()
        logger.info("Account picker opened.")

        # Find target index — UIA returns ALL items including scrolled-off ones
        items = win.descendants(control_type="ListItem")
        target_index = -1
        for i, item in enumerate(items):
            try:
                if email.lower() in item.window_text().lower():
                    target_index = i
                    logger.info(f"Found '{email}' at list index {i}.")
                    break
            except Exception:
                continue

        if target_index == -1:
            logger.error(f"Account '{email}' not found in picker.")
            return

        # Focus the list control and go to top
        try:
            list_ctrl = win.child_window(control_type="List")
            list_ctrl.set_focus()
        except Exception:
            win.set_focus()

        win.type_keys("{HOME}")
        time.sleep(0.3)

        # Press DOWN exactly target_index times to land on the right item
        for _ in range(target_index):
            try:
                list_ctrl.type_keys("{DOWN}")
            except Exception:
                win.type_keys("{DOWN}")
            time.sleep(0.15)

        time.sleep(0.5)
        logger.info(f"Navigated to '{email}' via keyboard.")

        # Click Continue
        try:
            btn = win.child_window(title="Continue", control_type="Button")
            btn.click_input()
            logger.info("Clicked Continue button.")
        except Exception:
            win.type_keys("{ENTER}")
            logger.info("Pressed Enter (Continue not found).")

    except Exception as e:
        logger.error(f"Failed to select account: {e}")


def dismiss_account_popup(timeout: int = 15):
    import win32gui, win32con

    logger.info("Checking for account confirmation popup...")

    start = time.time()
    while time.time() - start < timeout:
        # Check for a separate popup window with relevant keywords
        popup_hwnds = []

        def _find(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).lower()
            if "confirm" in title or "purchase" in title or "microsoft store" in title:
                popup_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        if popup_hwnds:
            hwnd = popup_hwnds[0]
            logger.info(f"Found popup: '{win32gui.GetWindowText(hwnd)}' — closing.")
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.info("Dismissed popup via WM_CLOSE.")
            time.sleep(0.5)
            return

        # Popup is inside Xbox — detect it by its specific button text, then press Escape
        xbox_hwnds = []

        def _find_xbox(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and "xbox" in win32gui.GetWindowText(hwnd).lower():
                xbox_hwnds.append(hwnd)

        win32gui.EnumWindows(_find_xbox, None)

        for hwnd in xbox_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue
            try:
                from pywinauto import Desktop as _Desktop
                xbox_win = _Desktop(backend="uia").window(handle=hwnd)
                for ctrl in xbox_win.descendants():
                    try:
                        txt = ctrl.window_text().strip().lower()
                        if "keep current" in txt:
                            _force_foreground(hwnd)
                            time.sleep(0.2)
                            ctrl.click_input()
                            logger.info("Clicked 'Keep current settings'.")
                            time.sleep(0.5)
                            return
                    except Exception:
                        continue
            except Exception:
                pass

        time.sleep(1)

    logger.info("No account confirmation popup detected — continuing.")


def click_lets_go(timeout: int = 20):
    import pyautogui
    import win32gui

    logger.info("Polling for 'Let's go' button...")

    start = time.time()
    while time.time() - start < timeout:
        xbox_hwnds = []

        def _collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and "xbox" in win32gui.GetWindowText(hwnd).lower():
                xbox_hwnds.append(hwnd)

        win32gui.EnumWindows(_collect, None)

        for hwnd in xbox_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            x = (rect[0] + rect[2]) // 2
            y = rect[3] - 40
            r, g, b = pyautogui.pixel(x, y)

            # Microsoft green button: G dominant, R and B low
            if g > 80 and r < 80 and b < 80:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.2)
                pyautogui.click(x, y)
                logger.info(f"Clicked 'Let's go' at ({x}, {y}).")
                return True

        time.sleep(0.5)

    logger.error("'Let's go' button did not appear within timeout — sign-in likely failed.")
    return False


def click_forza(timeout: int = 30):
    import pyautogui
    import win32gui

    logger.info("Polling for Forza icon...")

    start = time.time()
    while time.time() - start < timeout:
        xbox_hwnds = []

        def _collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and "xbox" in win32gui.GetWindowText(hwnd).lower():
                xbox_hwnds.append(hwnd)

        win32gui.EnumWindows(_collect, None)

        for hwnd in xbox_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            # Bring to front so pixel() reads the actual Xbox window
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # Try UIA text search first
            try:
                from pywinauto import Desktop as _Desktop
                xbox_win = _Desktop(backend="uia").window(handle=hwnd)
                for ctrl in xbox_win.descendants():
                    try:
                        if "forza" in ctrl.window_text().lower():
                            ctrl.click_input()
                            logger.info("Clicked Forza via UIA.")
                            return
                    except Exception:
                        continue
            except Exception:
                pass

            # Pixel check — log value so we can debug position if needed
            x = rect[0] + int(w * 0.15)
            y = rect[1] + int(h * 0.65)
            r, g, b = pyautogui.pixel(x, y)
            logger.info(f"Forza pixel at ({x},{y}): RGB({r},{g},{b})")

            if r > 60 or g > 60 or b > 60:
                pyautogui.click(x, y)
                logger.info(f"Clicked Forza icon at ({x}, {y}).")
                return
            break

        time.sleep(0.5)

    logger.error("Forza icon did not appear within timeout.")


def click_play(timeout: int = 30):
    import pyautogui
    import win32gui

    logger.info("Polling for Play button...")
    time.sleep(2)  # let Forza page render

    start = time.time()
    while time.time() - start < timeout:
        xbox_hwnds = []

        def _collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and "xbox" in win32gui.GetWindowText(hwnd).lower():
                xbox_hwnds.append(hwnd)

        win32gui.EnumWindows(_collect, None)

        for hwnd in xbox_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # Try UIA first
            try:
                from pywinauto import Desktop as _Desktop
                xbox_win = _Desktop(backend="uia").window(handle=hwnd)
                for ctrl in xbox_win.descendants():
                    try:
                        if ctrl.window_text().strip().lower() == "play":
                            ctrl.click_input()
                            logger.info("Clicked Play via UIA.")
                            return
                    except Exception:
                        continue
            except Exception:
                pass

            # Screenshot the Xbox window and scan for any green pixel (Play button)
            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            # Scan content area: x from 20%-50%, y from 20%-55% at 4px steps
            x_start, x_end = int(w * 0.20), int(w * 0.50)
            y_start, y_end = int(h * 0.20), int(h * 0.55)
            for sy in range(y_start, y_end, 4):
                for sx in range(x_start, x_end, 4):
                    r, g, b = px[sx, sy]
                    if g > 80 and r < 80 and b < 80:
                        click_x, click_y = rect[0] + sx, rect[1] + sy
                        pyautogui.click(click_x, click_y)
                        logger.info(f"Clicked Play (green scan) at ({click_x}, {click_y}).")
                        return
            break

        time.sleep(1)

    logger.error("Play button did not appear within timeout.")


def click_forza_taskbar(wait_seconds: int = 3):
    import win32gui

    logger.info(f"Waiting {wait_seconds}s then clicking Forza in taskbar...")
    time.sleep(wait_seconds)

    try:
        from pywinauto import Desktop as _Desktop
        taskbar = _Desktop(backend="uia").window(class_name="Shell_TrayWnd")
        for ctrl in taskbar.descendants():
            try:
                if "forza" in ctrl.window_text().lower():
                    ctrl.click_input()
                    logger.info("Clicked Forza in taskbar.")
                    return
            except Exception:
                continue

        # Fallback: find Forza window directly and bring to foreground
        forza_hwnd = win32gui.FindWindow(None, None)
        found = []

        def _find(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and "forza" in win32gui.GetWindowText(hwnd).lower():
                found.append(hwnd)

        win32gui.EnumWindows(_find, None)
        if found:
            win32gui.SetForegroundWindow(found[0])
            logger.info(f"Brought Forza window to foreground: '{win32gui.GetWindowText(found[0])}'")
            return

        logger.error("Forza not found in taskbar or open windows.")
    except Exception as e:
        logger.error(f"Failed to click Forza in taskbar: {e}")


def _force_foreground(hwnd):
    import ctypes
    import win32gui
    import win32con
    import win32process

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(0.2)

    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

    if current_thread != target_thread:
        ctypes.windll.user32.AttachThreadInput(target_thread, current_thread, True)

    win32gui.SetForegroundWindow(hwnd)
    win32gui.BringWindowToTop(hwnd)

    if current_thread != target_thread:
        ctypes.windll.user32.AttachThreadInput(target_thread, current_thread, False)


def click_ignore(wait_seconds: int = 10, timeout: int = 60):
    import win32gui

    logger.info(f"Waiting {wait_seconds}s then looking for compatibility warning...")
    time.sleep(wait_seconds)

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
            logger.info(f"Found window: '{title}' — forcing to front...")
            try:
                _force_foreground(hwnd)
            except Exception as e:
                logger.warning(f"force_foreground failed: {e}")
            time.sleep(0.4)

            try:
                from pywinauto import Desktop as _Desktop
                win = _Desktop(backend="uia").window(handle=hwnd)
                for ctrl in win.descendants():
                    try:
                        if "ignore" in ctrl.window_text().strip().lower():
                            ctrl.click_input()
                            logger.info("Clicked Ignore button.")
                            return
                    except Exception:
                        continue
            except Exception:
                pass

        time.sleep(0.5)

    logger.error("Compatibility warning did not appear within timeout.")


def press_alt_enter(wait_seconds: int = 10):
    import pyautogui

    logger.info(f"Waiting {wait_seconds}s then pressing Alt+Enter...")
    time.sleep(wait_seconds)
    pyautogui.hotkey("alt", "enter")
    logger.info("Pressed Alt+Enter.")


def spam_enter_after_altenter(duration: int = 30):
    import pyautogui

    logger.info(f"Spamming Enter for {duration}s...")
    end = time.time() + duration
    while time.time() < end:
        pyautogui.press("enter")
        time.sleep(0.15)
    logger.info("Done spamming Enter.")


def press_enter_start_game(timeout: int = 120):
    import pyautogui
    import win32gui

    logger.info("Waiting for 'Start Game' screen...")

    start = time.time()
    while time.time() - start < timeout:
        forza_hwnds = []

        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and "forza" in title.lower() and "xbox" not in title.lower():
                forza_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        for hwnd in forza_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            try:
                _force_foreground(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # "Start Game" text sits at bottom-left ~8% from left, ~87% from top
            x = rect[0] + int(w * 0.08)
            y = rect[1] + int(h * 0.87)
            r, g, b = pyautogui.pixel(x, y)
            logger.info(f"Start screen pixel at ({x},{y}): RGB({r},{g},{b})")

            if r > 180 and g > 180 and b > 180:
                time.sleep(0.3)
                pyautogui.press("enter")
                logger.info("Pressed Enter to start game.")
                return
            break

        time.sleep(0.5)

    logger.error("Start game screen did not appear within timeout.")


def spam_enter_setup(timeout: int = 60, spam_duration: int = 15):
    import pyautogui
    import win32gui

    logger.info("Waiting for Initial Setup menu...")

    start = time.time()
    while time.time() - start < timeout:
        forza_hwnds = []

        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and "forza" in title.lower() and "xbox" not in title.lower():
                forza_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        for hwnd in forza_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            try:
                _force_foreground(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # "Initial Setup" white title sits at ~34% from left, ~22% from top
            x = rect[0] + int(w * 0.34)
            y = rect[1] + int(h * 0.22)
            r, g, b = pyautogui.pixel(x, y)
            logger.info(f"Setup screen pixel at ({x},{y}): RGB({r},{g},{b})")

            if r > 180 and g > 180 and b > 180:
                logger.info(f"Initial Setup detected — spamming Enter for {spam_duration}s...")
                end = time.time() + spam_duration
                while time.time() < end:
                    pyautogui.press("enter")
                    time.sleep(0.15)
                logger.info("Done spamming Enter.")
                return
            break

        time.sleep(0.5)

    logger.error("Initial Setup screen did not appear within timeout.")


def press_enter_low_memory(timeout: int = 120):
    import pyautogui
    import win32gui

    logger.info("Waiting for 'Low Video Memory' dialog...")

    start = time.time()
    while time.time() - start < timeout:
        forza_hwnds = []

        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and "forza" in title.lower() and "xbox" not in title.lower():
                forza_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        for hwnd in forza_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            try:
                _force_foreground(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # Scan whole window for the bright yellow-green header (R>150, G>200, B<80)
            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            found = False
            for sy in range(0, h, 4):
                for sx in range(0, w, 4):
                    r, g, b = px[sx, sy]
                    if r > 150 and g > 200 and b < 80:
                        found = True
                        break
                if found:
                    break

            if found:
                logger.info("Low Video Memory dialog detected.")
                pyautogui.press("enter")
                logger.info("Pressed Enter.")
                time.sleep(0.5)
                pyautogui.press("escape")
                logger.info("Pressed Escape.")
                logger.info("Waiting 2 minutes before pressing 8...")
                time.sleep(120)
                pyautogui.hotkey("ctrl", "8")
                logger.info("Pressed 8.")
                return
            break

        time.sleep(1)

    logger.error("Low Video Memory dialog did not appear within timeout.")


def close_xbox():
    import win32gui, win32con

    hwnds = []

    def _find(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and "xbox" in win32gui.GetWindowText(hwnd).lower():
            hwnds.append(hwnd)

    win32gui.EnumWindows(_find, None)
    for hwnd in hwnds:
        rect = win32gui.GetWindowRect(hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w > 200 and h > 200:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.info("Xbox window closed.")
            return
    logger.warning("Xbox window not found to close.")


def wait_then_close_forza(wait_minutes: int = 20):
    import win32gui, win32con, win32process, ctypes

    logger.info(f"Waiting {wait_minutes} minutes before closing Forza...")
    time.sleep(wait_minutes * 60)

    forza_hwnds = []

    def _find(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and "forza" in title.lower() and "xbox" not in title.lower():
            forza_hwnds.append(hwnd)

    win32gui.EnumWindows(_find, None)

    if not forza_hwnds:
        logger.warning("Forza window not found — may already be closed.")
        return

    hwnd = forza_hwnds[0]

    # Get PID now before the window disappears
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        pid = None

    # Step 1: graceful Alt+F4
    try:
        _force_foreground(hwnd)
        time.sleep(0.3)
        pyautogui.hotkey("alt", "f4")
        logger.info("Sent Alt+F4 to Forza.")
        time.sleep(3)
    except Exception:
        pass

    # Step 2: WM_CLOSE if still alive
    try:
        if win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.info("Sent WM_CLOSE to Forza.")
            time.sleep(2)
    except Exception:
        pass

    # Step 3: kill process by PID as guarantee
    if pid:
        try:
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
                logger.info(f"Terminated Forza process (PID {pid}).")
        except Exception as e:
            logger.warning(f"Process kill failed: {e}")


def wait_for_world_map_and_close(initial_wait: int = 600, timeout: int = 600):
    import pyautogui
    import win32gui

    logger.info(f"Waiting {initial_wait // 60} min before checking for World Map screen...")
    time.sleep(initial_wait)
    logger.info("Now polling for World Map screen (pink menu cards)...")

    start = time.time()
    while time.time() - start < timeout:
        forza_hwnds = []

        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and "forza" in title.lower() and "xbox" not in title.lower():
                forza_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        for hwnd in forza_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            try:
                _force_foreground(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # Scan for distinctive pink/magenta of the World Map menu cards
            shot = pyautogui.screenshot(region=(rect[0], rect[1], w, h))
            px = shot.load()
            found = False
            for sy in range(int(h * 0.50), int(h * 0.90), 4):
                for sx in range(int(w * 0.05), int(w * 0.95), 4):
                    r, g, b = px[sx, sy]
                    if r > 180 and g < 80 and b > 80:
                        found = True
                        break
                if found:
                    break

            if found:
                logger.info("World Map screen detected — closing Forza with Alt+F4.")
                pyautogui.hotkey("alt", "f4")
                logger.info("Forza closed.")
                return
            break

        time.sleep(2)

    logger.error("World Map screen did not appear within timeout.")


def press_escape_then_9(timeout: int = 120):
    import pyautogui
    import win32gui

    logger.info("Waiting for controller mapping screen...")

    start = time.time()
    while time.time() - start < timeout:
        forza_hwnds = []

        def _find(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and "forza" in title.lower() and "xbox" not in title.lower():
                forza_hwnds.append(hwnd)

        win32gui.EnumWindows(_find, None)

        for hwnd in forza_hwnds:
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 200 or h < 200:
                continue

            try:
                _force_foreground(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            # Teal background — check top-right area away from UI elements
            x = rect[0] + int(w * 0.80)
            y = rect[1] + int(h * 0.15)
            r, g, b = pyautogui.pixel(x, y)
            logger.info(f"Controller screen pixel at ({x},{y}): RGB({r},{g},{b})")

            # Teal: low R (~38), G dominant (~113), B mid (~96) — based on observed pixel
            if r < 60 and g > 90 and b > 60 and g > r * 2:
                pyautogui.press("escape")
                logger.info("Pressed Escape on controller screen.")
                time.sleep(1)
                pyautogui.press("9")
                logger.info("Pressed 9.")
                return
            break

        time.sleep(0.5)

    logger.error("Controller mapping screen did not appear within timeout.")
