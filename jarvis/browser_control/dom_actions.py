"""
dom_actions.py — All direct DOM/browser interactions via Playwright.

Design principles:
  - Every public method returns a value or False/None on failure.
  - Methods NEVER raise exceptions to the caller; errors are logged internally.
  - DOM-based actions are the PRIMARY mechanism; vision/coordinates are fallback.
  - take_screenshot() returns PIL.Image — faster than pyautogui for browser captures.
"""

import io
import logging
from typing import Optional

from PIL import Image
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger("browser_control.dom_actions")


class DOMActions:
    """
    Thin, reliable wrapper around a Playwright Page object.

    All timeout values are in milliseconds (Playwright default).
    """

    def __init__(self, page: Page):
        self.page = page

    # ── Navigation ────────────────────────────────────────────────────────────

    def goto(self, url: str) -> str:
        """
        Navigate to *url*.  Prepends https:// if no scheme is present.
        Returns the page title after navigation; '' on failure.
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            return self.page.title()
        except Exception as e:
            logger.warning(f"goto({url}) failed: {e}")
            return ""

    def get_current_url(self) -> str:
        """Return the current page URL."""
        return self.page.url

    def go_back(self) -> None:
        """Navigate back in browser history."""
        try:
            self.page.go_back()
        except Exception as e:
            logger.warning(f"go_back() failed: {e}")

    def go_forward(self) -> None:
        """Navigate forward in browser history."""
        try:
            self.page.go_forward()
        except Exception as e:
            logger.warning(f"go_forward() failed: {e}")

    def reload(self) -> None:
        """Reload the current page."""
        try:
            self.page.reload()
        except Exception as e:
            logger.warning(f"reload() failed: {e}")

    # ── Interaction ───────────────────────────────────────────────────────────

    def click(
        self,
        selector: Optional[str] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> bool:
        """
        Click an element by *selector* OR by absolute coordinates (*x*, *y*).
        Returns True on success, False on timeout/not-found.
        Raises ValueError if neither selector nor coordinates are provided.
        """
        if selector is not None:
            try:
                self.page.click(selector, timeout=5_000)
                return True
            except PlaywrightTimeout:
                logger.warning(f"click(selector={selector!r}) timed out")
                return False
            except Exception as e:
                logger.warning(f"click(selector={selector!r}) error: {e}")
                return False

        if x is not None and y is not None:
            try:
                self.page.mouse.click(x, y)
                return True
            except Exception as e:
                logger.warning(f"click(x={x}, y={y}) error: {e}")
                return False

        raise ValueError("click() requires either 'selector' or 'x' and 'y' coordinates.")

    def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
    ) -> bool:
        """
        Type *text* into the element identified by *selector*.

        If *clear_first* is True the field is cleared before typing.
        Uses a 30 ms per-key delay for human-like input.
        Returns True on success, False on timeout/not-found.
        """
        try:
            self.page.wait_for_selector(selector, timeout=5_000)
            if clear_first:
                self.page.fill(selector, "")
            self.page.type(selector, text, delay=30)
            return True
        except PlaywrightTimeout:
            logger.warning(f"type_text(selector={selector!r}) timed out waiting for element")
            return False
        except Exception as e:
            logger.warning(f"type_text(selector={selector!r}) error: {e}")
            return False

    def press_key(self, key: str) -> None:
        """
        Send a keyboard event.  Supports single keys and modifiers, e.g.:
          "Enter", "Tab", "Escape", "ctrl+c", "ctrl+v", "ArrowDown"
        """
        try:
            self.page.keyboard.press(key)
        except Exception as e:
            logger.warning(f"press_key({key!r}) error: {e}")

    def scroll_page(self, direction: str = "down", amount: int = 3) -> None:
        """
        Scroll the page using the mouse wheel.
        *amount* is a multiplier; one unit ≈ 300 px.
        """
        delta = 300 * amount
        try:
            if direction == "down":
                self.page.mouse.wheel(0, delta)
            else:
                self.page.mouse.wheel(0, -delta)
        except Exception as e:
            logger.warning(f"scroll_page(direction={direction!r}, amount={amount}) error: {e}")

    def hover(self, selector: str) -> bool:
        """
        Move the mouse over *selector*.
        Returns True on success, False on timeout.
        """
        try:
            self.page.hover(selector, timeout=3_000)
            return True
        except PlaywrightTimeout:
            logger.warning(f"hover(selector={selector!r}) timed out")
            return False
        except Exception as e:
            logger.warning(f"hover(selector={selector!r}) error: {e}")
            return False

    def select_option(self, selector: str, value: str) -> bool:
        """
        Select an `<option>` inside a `<select>` by its *value* attribute.
        Returns True on success, False on failure.
        """
        try:
            self.page.select_option(selector, value)
            return True
        except Exception as e:
            logger.warning(f"select_option(selector={selector!r}, value={value!r}) error: {e}")
            return False

    # ── Reading / scraping ────────────────────────────────────────────────────

    def get_text(self, selector: str) -> Optional[str]:
        """
        Return the inner text of the element matched by *selector*.
        Returns None if not found or on error.
        """
        try:
            return self.page.inner_text(selector, timeout=3_000)
        except Exception as e:
            logger.warning(f"get_text(selector={selector!r}) error: {e}")
            return None

    def get_page_text(self) -> str:
        """
        Return the full inner text of <body>.
        Used to give Gemini complete page content without a screenshot.
        """
        try:
            return self.page.inner_text("body")
        except Exception as e:
            logger.warning(f"get_page_text() error: {e}")
            return ""

    def get_all_links(self) -> list[dict]:
        """
        Return a list of {text, href} for every anchor tag on the page.
        Filters out empty hrefs and javascript: pseudo-links.
        """
        try:
            raw: list[dict] = self.page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => ({ text: a.innerText.trim(), href: a.href }))
            """)
            return [
                link for link in raw
                if link.get("href")
                and not link["href"].startswith("javascript:")
                and link["href"] != "about:blank"
            ]
        except Exception as e:
            logger.warning(f"get_all_links() error: {e}")
            return []

    def find_element_by_text(self, text: str) -> Optional[str]:
        """
        Find the first element whose visible text contains *text* (case-insensitive).
        Returns a CSS selector string on success, None if not found.

        Note: uses Playwright's locator API internally; the returned 'selector'
        is a description string, not a guarantee that the same locator will match
        next time if the DOM changed.
        """
        try:
            locator = self.page.get_by_text(text, exact=False).first
            # Verify it actually exists before returning
            locator.wait_for(timeout=3_000)
            # Build a best-effort selector string
            tag = locator.evaluate("el => el.tagName.toLowerCase()")
            return f'{tag}:has-text("{text}")'
        except Exception as e:
            logger.debug(f"find_element_by_text({text!r}) not found: {e}")
            return None

    def take_screenshot(self) -> Image.Image:
        """
        Capture the visible viewport as a PIL.Image.
        Much faster than pyautogui because it reads directly from the browser
        render pipeline without involving the OS screenshot API.
        """
        try:
            raw = self.page.screenshot(full_page=False)
            return Image.open(io.BytesIO(raw))
        except Exception as e:
            logger.warning(f"take_screenshot() error: {e}")
            # Return a minimal 1×1 white image so callers never get None
            return Image.new("RGB", (1, 1), (255, 255, 255))

    def get_page_info(self) -> dict:
        """
        Return a lightweight info snapshot of the current page.
        This is sent to Gemini on every step alongside the screenshot,
        allowing text-based reasoning rather than pure pixel analysis.
        """
        try:
            title = self.page.title()
        except Exception:
            title = ""

        try:
            text_preview = self.page.inner_text("body")[:2000]
        except Exception:
            text_preview = ""

        try:
            input_count: int = self.page.evaluate(
                "() => document.querySelectorAll('input, textarea').length"
            )
        except Exception:
            input_count = 0

        try:
            button_count: int = self.page.evaluate(
                "() => document.querySelectorAll('button, [role=\"button\"], [type=\"submit\"]').length"
            )
        except Exception:
            button_count = 0

        try:
            link_count: int = self.page.evaluate(
                "() => document.querySelectorAll('a[href]').length"
            )
        except Exception:
            link_count = 0

        return {
            "url": self.page.url,
            "title": title,
            "text_preview": text_preview,
            "input_fields": input_count,
            "button_count": button_count,
            "links": link_count,
        }

    # ── Waiting ───────────────────────────────────────────────────────────────

    def wait_for_navigation(self, timeout: int = 10_000) -> bool:
        """
        Wait for the page to reach 'domcontentloaded' state.
        Returns True on success, False on timeout.
        """
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
            return True
        except PlaywrightTimeout:
            logger.warning("wait_for_navigation() timed out")
            return False
        except Exception as e:
            logger.warning(f"wait_for_navigation() error: {e}")
            return False

    def wait_for_element(self, selector: str, timeout: int = 5_000) -> bool:
        """
        Wait until *selector* appears in the DOM.
        Returns True if found within *timeout* ms, False otherwise.
        """
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except PlaywrightTimeout:
            logger.warning(f"wait_for_element(selector={selector!r}) timed out")
            return False
        except Exception as e:
            logger.warning(f"wait_for_element(selector={selector!r}) error: {e}")
            return False
