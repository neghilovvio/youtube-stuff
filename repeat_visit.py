#!/usr/bin/env python3
"""
repeat_visit.py

Cross-platform repeated-visit tester.

Features:
- Selenium 4 (Chrome/Firefox/Edge) with Selenium Manager (no manual driver)
- Optional headless mode
- Reuse a single browser (much faster) or launch per view
- Simple per-view interaction: none | space | scroll | click
- System-browser mode (no Selenium) for quick opens without killing processes

Usage examples:
  python repeat_visit.py --url https://example.com --views 5 --duration 3
  python repeat_visit.py --url https://example.com --views 10 --duration 2 --browser chrome --headless
  python repeat_visit.py --url https://example.com --views 5 --duration 2 --interaction scroll
  python repeat_visit.py --url https://example.com --views 5 --duration 1 --mode system-browser

"""

import argparse
import time
import sys
from typing import Optional

# --- Optional fallback if user chooses system-browser mode ---
import webbrowser

# --- Selenium imports are optional; only needed in selenium mode ---
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import WebDriverException
except Exception:
    webdriver = None  # we’ll check this at runtime when needed


def build_driver(browser: str, headless: bool) -> "webdriver.Remote":
    """
    Create a Selenium 4 driver instance using Selenium Manager.
    """
    browser = browser.lower()
    if browser not in ("chrome", "firefox", "edge"):
        raise ValueError("browser must be one of: chrome, firefox, edge")

    if browser == "chrome":
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        opts = ChromeOptions()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=opts)

    elif browser == "firefox":
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        opts = FirefoxOptions()
        if headless:
            opts.add_argument("-headless")
        driver = webdriver.Firefox(options=opts)

    else:  # edge
        from selenium.webdriver.edge.options import Options as EdgeOptions
        opts = EdgeOptions()
        if headless:
            opts.add_argument("--headless=new")
        driver = webdriver.Edge(options=opts)

    # Make page loads a bit more resilient
    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)
    return driver


def do_interaction(driver, interaction: str, click_selector: Optional[str]) -> None:
    """
    Perform a simple interaction on the page to simulate activity.
    """
    interaction = interaction.lower()
    if interaction == "none":
        return

    if interaction == "space":
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.SPACE)

    elif interaction == "scroll":
        # Scroll down, then up a bit
        driver.execute_script("window.scrollBy(0, Math.max(200, window.innerHeight/2));")
        time.sleep(0.2)
        driver.execute_script("window.scrollBy(0, Math.max(200, window.innerHeight/2));")
        time.sleep(0.2)
        driver.execute_script("window.scrollBy(0, -100);")

    elif interaction == "click":
        if not click_selector:
            # Try a common “play” button guess, otherwise just click body
            selectors = [
                '[aria-label="Play"]',
                '[data-testid="play-button"]',
                'button[title*="Play" i]',
                'button[aria-label*="play" i]',
                "video",
            ]
        else:
            selectors = [click_selector]

        clicked = False
        for sel in selectors:
            try:
                el = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                el.click()
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            # As a last resort, send a space (often toggles media)
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SPACE)
            except Exception:
                pass

    else:
        raise ValueError("interaction must be one of: none, space, scroll, click")


def accept_google_consent(driver) -> None:
    """
    Wait for Google/YouTube consent modal to appear (up to ~20s) and click
    an "Accept all"/"I agree" button. Handles consent presented inside iframes.

    Safe to call multiple times; exits quickly if nothing is found.
    """
    def _try_click_in_current_context() -> bool:
        # Try robust JS text/aria search
        try:
            clicked = driver.execute_script(
                """
                const texts = ["Accept all", "I agree", "I'm OK with that", "Accept", "Agree", "Accept All"];
                function findButton() {
                  const buttons = Array.from(document.querySelectorAll('button, tp-yt-paper-button'));
                  for (const b of buttons) {
                    const label = (b.getAttribute('aria-label')||'').toLowerCase();
                    if (label.includes('accept all') || label.includes('i agree') || label.includes('accept')) return b;
                    const txt = (b.innerText||b.textContent||'').trim().toLowerCase();
                    if (texts.some(t => txt.includes(t.toLowerCase()))) return b;
                  }
                  return null;
                }
                const btn = findButton();
                if (btn) { btn.click(); return true; }
                return false;
                """
            )
            if clicked:
                return True
        except Exception:
            pass

        # Try common CSS selectors
        css_candidates = [
            'button[aria-label*="Accept all" i]',
            'button[aria-label="Accept all"]',
            'button[aria-label*="I agree" i]',
            'button#introAgreeButton',
            'div[role="dialog"] button',
            'button.yt-spec-button-shape-next__button',
        ]
        for sel in css_candidates:
            try:
                el = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                # Validate button text if possible
                txt = (el.text or "").lower()
                aria = (el.get_attribute('aria-label') or "").lower()
                if any(t in txt for t in ["accept", "agree"]) or any(t in aria for t in ["accept", "agree"]):
                    el.click()
                    return True
            except Exception:
                continue
        return False

    # Wait for modal presence and attempt clicking, including inside iframes
    end_time = time.time() + 20.0
    switched = False
    while time.time() < end_time:
        try:
            # First, try in the main document
            if _try_click_in_current_context():
                if switched:
                    driver.switch_to.default_content()
                return

            # Then, look for likely consent iframes and try inside them
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe")
            for f in frames:
                try:
                    src = (f.get_attribute("src") or "").lower()
                    title = (f.get_attribute("title") or "").lower()
                    if (
                        any(k in src for k in ["consent.", "consent.youtube", "consent.google"]) or
                        any(k in title for k in ["consent", "privacy", "agree"])
                    ):
                        driver.switch_to.frame(f)
                        switched = True
                        if _try_click_in_current_context():
                            driver.switch_to.default_content()
                            return
                        driver.switch_to.default_content()
                        switched = False
                except Exception:
                    # Cross-origin or detached frame
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass
                    switched = False
                    continue
        except Exception:
            pass

        time.sleep(0.5)
    # If we exit the loop, consent likely not present; proceed gracefully


def ensure_video_playing(driver) -> None:
    """
    Try to start playback for an HTML5 <video> (e.g., YouTube). Tries JS .play(),
    clicking common play buttons, and keyboard shortcuts ('k').
    """
    try:
        # Prefer explicit JS play on all videos
        driver.execute_script(
            """
            const vids = Array.from(document.querySelectorAll('video'));
            for (const v of vids) { try { v.muted = v.muted || false; v.play().catch(()=>{}); } catch(e){} }
            return vids.length;
            """
        )
    except Exception:
        pass

    # Try clicking YouTube player button
    for sel in [
        'button.ytp-play-button',
        '#movie_player button[aria-label*="Play" i]',
        '[aria-label="Play"]',
        'video',
    ]:
        try:
            el = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            el.click()
            break
        except Exception:
            continue

    # Keyboard fallback ('k' toggles play on YouTube)
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys('k')
    except Exception:
        pass


def wait_until_video_ended(driver, hard_cap_seconds: int = 4 * 3600) -> None:
    """
    Poll the page until a <video> reports ended=true or currentTime >= duration.
    Uses a generous safety hard cap to avoid infinite waits.
    """
    start = time.time()
    last_progress_time = start
    last_current_time = -1.0

    # Wait for video to be ready (duration > 0)
    for _ in range(60):
        try:
            ready = driver.execute_script(
                """
                const vids = Array.from(document.querySelectorAll('video'));
                for (const v of vids) {
                  if (!isNaN(v.duration) && v.duration > 0) { return true; }
                }
                return false;
                """
            )
            if ready:
                break
        except Exception:
            pass
        time.sleep(0.5)

    # Main poll loop
    while True:
        try:
            ended = driver.execute_script(
                """
                const vids = Array.from(document.querySelectorAll('video'));
                let maxDur = 0, cur = 0, ended = false;
                for (const v of vids) {
                  const d = (isNaN(v.duration) ? 0 : v.duration);
                  maxDur = Math.max(maxDur, d);
                  cur = Math.max(cur, v.currentTime || 0);
                  ended = ended || v.ended === true || (d > 0 && cur >= d - 0.25);
                }
                return { ended, cur, duration: maxDur };
                """
            )
            if ended and isinstance(ended, dict):
                if ended.get('ended'):
                    return
                cur = float(ended.get('cur', 0) or 0)
            else:
                # Fallback if structure changes
                cur = 0.0
        except Exception:
            cur = 0.0

        now = time.time()
        if cur > last_current_time + 0.5:
            last_current_time = cur
            last_progress_time = now

        # Stalled for > 2 minutes: try to re-trigger play once
        if now - last_progress_time > 120:
            ensure_video_playing(driver)
            last_progress_time = now

        if now - start > hard_cap_seconds:
            return

        time.sleep(2.0)


def run_selenium_mode(
    url: str,
    views: int,
    duration: float,
    browser: str,
    headless: bool,
    reuse: bool,
    interaction: str,
    click_selector: Optional[str],
    reload_between_views: bool,
    watch_until_end: bool,
) -> None:
    if webdriver is None:
        raise RuntimeError(
            "Selenium is not installed. Install with: pip install selenium"
        )

    if reuse:
        # One browser reused across views (fast & light)
        driver = build_driver(browser, headless)
        try:
            for i in range(1, views + 1):
                driver.get(url)
                # Wait for document ready
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except Exception:
                    pass

                # Handle consent and start playback if requested
                accept_google_consent(driver)
                if watch_until_end:
                    ensure_video_playing(driver)
                    wait_until_video_ended(driver)
                else:
                    do_interaction(driver, interaction, click_selector)
                    time.sleep(duration)

                if reload_between_views:
                    try:
                        driver.refresh()
                        WebDriverWait(driver, 20).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        accept_google_consent(driver)
                    except Exception:
                        pass

                print(f"{i}/{views} views done")
        finally:
            try:
                driver.quit()
            except Exception:
                pass
    else:
        # Launch per view (heavier, but isolates sessions completely)
        for i in range(1, views + 1):
            driver = build_driver(browser, headless)
            try:
                driver.get(url)
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except Exception:
                    pass

                accept_google_consent(driver)
                if watch_until_end:
                    ensure_video_playing(driver)
                    wait_until_video_ended(driver)
                else:
                    do_interaction(driver, interaction, click_selector)
                    time.sleep(duration)
                print(f"{i}/{views} views done")
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass


def run_system_browser_mode(url: str, views: int, duration: float) -> None:
    """
    Cross-platform system browser approach that DOES NOT kill processes.
    Opens a new tab (or window) repeatedly and sleeps between opens.
    """
    controller = webbrowser.get()  # default system browser
    for i in range(1, views + 1):
        # Use new window for the first open, then new tabs
        if i == 1:
            controller.open_new(url)
        else:
            controller.open_new_tab(url)
        time.sleep(duration)
        print(f"{i}/{views} opens done")


def main():
    parser = argparse.ArgumentParser(description="Repeated-visit tester")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--views", type=int, default=5, help="Number of views (default: 5)")
    parser.add_argument("--duration", type=float, default=3.0,
                        help="Seconds to wait per view (default: 3.0)")
    parser.add_argument("--mode", choices=["selenium", "system-browser"],
                        default="selenium", help="Run with Selenium or the system browser")
    parser.add_argument("--browser", choices=["chrome", "firefox", "edge"],
                        default="firefox", help="Selenium browser choice (default: firefox)")
    parser.add_argument("--headless", action="store_true", help="Run browser headless (Selenium only)")
    parser.add_argument("--reuse", action="store_true",
                        help="Reuse a single Selenium browser across views (faster)")
    parser.add_argument("--interaction", choices=["none", "space", "scroll", "click"],
                        default="none", help="Per-view interaction (Selenium only)")
    parser.add_argument("--click-selector", default=None,
                        help="CSS selector to click when --interaction=click")
    parser.add_argument("--reload-between-views", action="store_true",
                        help="Refresh the page after each view (Selenium only)")
    parser.add_argument("--watch-until-end", action="store_true",
                        help="For pages with <video> (e.g., YouTube), start playback and wait until the video ends")

    args = parser.parse_args()

    if args.mode == "system-browser":
        run_system_browser_mode(args.url, args.views, args.duration)
        return

    # Selenium mode
    try:
        run_selenium_mode(
            url=args.url,
            views=args.views,
            duration=args.duration,
            browser=args.browser,
            headless=args.headless,
            reuse=args.reuse,
            interaction=args.interaction,
            click_selector=args.click_selector,
            reload_between_views=args.reload_between_views,
            watch_until_end=args.watch_until_end,
        )
    except WebDriverException as e:
        print("Selenium WebDriver error:", e, file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
