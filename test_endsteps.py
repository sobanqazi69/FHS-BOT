"""
Quick test script — skips login & game launch.
Just runs the final steps:
  1. Close Xbox
  2. Open FH6 SAFE SWAP folder
  3. Launch ForzaCryptoTool.exe
"""
import time
import subprocess
import logging
import sys

from bot.modules.ui_controller import close_xbox

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

logger.info("TEST: Closing Xbox...")
try:
    close_xbox()
except Exception as e:
    logger.warning(f"close_xbox() skipped (Xbox may not be open): {e}")


logger.info("TEST: Opening FH6 SAFE SWAP folder...")
subprocess.Popen(["explorer", r"C:\Users\pc\Desktop\FH6 SAFE SWAP"])
time.sleep(2)

logger.info("TEST: Launching ForzaCryptoTool.exe...")
subprocess.Popen([r"C:\Users\pc\Desktop\FH6 SAFE SWAP\ForzaCryptoTool.exe"])

logger.info("Waiting 5s for ForzaCryptoTool to load...")
time.sleep(5)

import win32gui, win32con

# Find and maximize the ForzaCryptoTool window
def _find_forza_tool(hwnd, results):
    if win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd)
        if "forzacryptotool" in title.lower() or "forza" in title.lower():
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
            import pyautogui as _pag
            _pag.click(x, y)
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
            # Fallback coords for first Browse button
            rect = win32gui.GetWindowRect(hwnd)
            import pyautogui as _pag
            _pag.click(rect[0] + 530, rect[1] + 168)
            logger.info("Clicked first Browse via pyautogui fallback.")

        # Handle the file open dialog — type the path and press Enter
        logger.info("Waiting for file dialog...")
        time.sleep(2)
        import pyautogui as _pag
        donor_path = r"C:\Users\pc\Desktop\FH6 SAFE SWAP\C_ProfileData"
        _pag.hotkey("ctrl", "a")
        time.sleep(0.2)
        _pag.typewrite(donor_path, interval=0.03)
        time.sleep(0.3)
        _pag.press("enter")
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
        _pag.hotkey("ctrl", "a")
        time.sleep(0.2)
        _pag.typewrite(active_path, interval=0.03)
        time.sleep(0.3)
        _pag.press("enter")
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
            _pag.click(rect[0] + 207, rect[1] + 372)
            logger.info("Clicked Auto-detect Active Save via pyautogui fallback.")

        # Wait for 'Select profile save' dialog and click 'Use selected'
        logger.info("Waiting for 'Select profile save' dialog...")
        time.sleep(3)
        use_selected_clicked = False
        for ctrl in tool_win.descendants():
            try:
                txt = ctrl.window_text().strip().lower()
                if "use selected" in txt:
                    ctrl.click_input()
                    logger.info("Clicked 'Use selected'.")
                    use_selected_clicked = True
                    break
            except Exception:
                pass

        if not use_selected_clicked:
            # Fallback: try finding dialog window directly
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
                _pag.press("enter")

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
            _pag.click(rect[0] + 314, rect[1] + 482)
            logger.info("Clicked Grab XUID via pyautogui fallback.")

        logger.info("Waiting 5s after Grab XUID...")
        time.sleep(5)

        def _check_xuid_success():
            """Return True if green 'XUID grabbed' text is visible."""
            for ctrl in tool_win.descendants():
                try:
                    if "xuid grabbed" in ctrl.window_text().strip().lower():
                        return True
                except Exception:
                    pass
            return False

        def _click_grab_xuid():
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
                _pag.click(rect[0] + 314, rect[1] + 482)
                logger.info("Clicked Grab XUID via pyautogui (retry fallback).")

        def _do_swap_save():
            """Click Swap Save, press Yes on popup, wait 10s."""
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
                _pag.click(rect[0] + 155, rect[1] + 610)
                logger.info("Clicked Swap Save via pyautogui fallback.")

            # Wait for confirmation popup and press Yes
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
                _pag.press("enter")
                logger.info("Pressed Enter as fallback for Yes.")

            logger.info("Waiting 40s after Swap Save (swap completing)...")
            time.sleep(40)

            # Open Xbox and launch game
            logger.info("Opening Xbox...")
            from bot.modules.app_launcher import open_xbox as _open_xbox
            from bot.modules.ui_controller import click_forza, click_play, click_ignore
            _open_xbox()

            logger.info("Launching Forza...")
            click_forza(timeout=30)
            click_play(timeout=30)

            logger.info("Waiting for and clicking ignore warning popup...")
            click_ignore(wait_seconds=30, timeout=60)

            logger.info("Waiting 35s after ignore...")
            time.sleep(35)

            logger.info("Spamming Enter for 10 seconds...")
            spam_end = time.time() + 10
            while time.time() < spam_end:
                _pag.press("enter")
                time.sleep(0.5)
            logger.info("Done spamming Enter.")

        # Check result and retry if needed
        if _check_xuid_success():
            logger.info("XUID grabbed successfully (green). Proceeding to Swap Save.")
            _do_swap_save()
        else:
            logger.warning("XUID grab failed (red text). Waiting 30s before retry...")
            time.sleep(30)
            _click_grab_xuid()
            logger.info("Waiting 5s after Grab XUID retry...")
            time.sleep(5)
            if _check_xuid_success():
                logger.info("XUID grabbed on retry (green). Proceeding to Swap Save.")
                _do_swap_save()
            else:
                logger.error("XUID grab failed after retry. Skipping Swap Save.")

    except Exception as e:
        logger.warning(f"pywinauto failed, falling back to win32/pyautogui: {e}")
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
        time.sleep(1)
        rect = win32gui.GetWindowRect(hwnd)
        x = rect[0] + 88
        y = rect[1] + 207
        import pyautogui as _pag
        _pag.click(x, y)
        logger.info(f"Clicked Save Swap at ({x}, {y}) via pyautogui.")
else:
    logger.warning("ForzaCryptoTool window not found.")


logger.info("TEST: Done.")
