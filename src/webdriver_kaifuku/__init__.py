"""Core functionality for starting, restarting, and stopping a selenium browser."""
from __future__ import annotations

import logging
from copy import copy
from typing import Callable
from typing import ClassVar
from urllib.error import URLError
from urllib.parse import urlparse

from attrs import define
from attrs import field
from selenium import webdriver
from selenium.common.exceptions import UnexpectedAlertPresentException
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.file_detector import UselessFileDetector
from selenium.webdriver.remote.webdriver import WebDriver

from .tries import tries

log = logging.getLogger(__name__)


THIRTY_SECONDS = 30

BROWSER_ERRORS = URLError, WebDriverException
TRUSTED_WEB_DRIVERS = [webdriver.Firefox, webdriver.Chrome, webdriver.Remote]


def _get_browser_name(webdriver_kwargs: dict, webdriver_name: str) -> str:
    """
    Extract the name of the browser from the browser config
    """
    if webdriver_name.lower() == "remote":
        name_from_options = (
            webdriver_kwargs["options"].to_capabilities().get("browserName")
            if "options" in webdriver_kwargs
            else None
        )
        name_from_desired_capabilities = webdriver_kwargs.get("desired_capabilities", {}).get(
            "browserName"
        )
        name = name_from_options or name_from_desired_capabilities
    else:
        name = webdriver_name
    if name:
        return name.lower()
    raise ValueError("No browser name specified")


def _remove_deprecated_items(browser_conf: dict) -> dict:
    """
    Remove deprecated items from browser config
    """
    deprecated_items = ["perfLoggingPrefs", "marionette"]
    opts = browser_conf.get("webdriver_options", {})
    if opts and "desired_capabilities" in opts:
        for i in deprecated_items:
            if i in opts["desired_capabilities"]:
                log.warning(
                    f"'{i}' capability has been deprecated in Selenium 4.10. "
                    f"Remove it from your browser config"
                )
                del browser_conf["webdriver_options"]["desired_capabilities"][i]
    return browser_conf


@define(auto_attribs=True)
class BrowserFactory:
    ALLOWED_KWARGS: ClassVar[list[str]] = ["command_executor", "options", "keep_alive"]
    webdriver_class: type
    webdriver_kwargs: dict

    def processed_browser_args(self):
        return {k: v for k, v in self.webdriver_kwargs.items() if k in self.ALLOWED_KWARGS}

    def create(self) -> WebDriver:
        try:
            browser = tries(
                2,
                WebDriverException,
                self.webdriver_class,
                **self.processed_browser_args(),
            )
        except URLError as e:
            if e.reason.errno == 111:  # type: ignore
                # Known issue
                raise RuntimeError("Could not connect to Selenium server. Is it up and running?")
            else:
                # Unknown issue
                raise

        browser.file_detector = UselessFileDetector()
        browser.maximize_window()
        return browser

    def close(self, browser: WebDriver | None) -> None:
        if browser:
            browser.quit()


@define(auto_attribs=True)
class BrowserManager:
    browser_factory: BrowserFactory
    browser: WebDriver | None = field(default=None, init=False)

    @staticmethod
    def _config_options_for_chrome(browser_conf: dict) -> webdriver.ChromeOptions:
        opts = browser_conf.get("webdriver_options", {}).get("options", webdriver.ChromeOptions())
        chrome_options = browser_conf.get("webdriver_options", {}).get("desired_capabilities", {})
        additional_chrome_opts = chrome_options.pop("chromeOptions", {})

        chrome_args = additional_chrome_opts.get("args", [])
        if chrome_args:
            for arg in chrome_args:
                if arg not in opts.arguments:
                    opts.add_argument(arg)
        if "proxy_url" in browser_conf:
            opts.add_argument(f"--proxy-server={browser_conf['proxy_url']}")
        for key, value in chrome_options.items():
            opts.set_capability(key, value)
        return opts

    @staticmethod
    def _config_options_for_firefox(browser_conf: dict) -> webdriver.FirefoxOptions:
        opts = browser_conf.get("webdriver_options", {}).get("options", webdriver.FirefoxOptions())
        firefox_options = browser_conf.get("webdriver_options", {}).get("desired_capabilities", {})
        additional_firefox_opts = firefox_options.pop("firefoxOptions", {})

        firefox_args = additional_firefox_opts.get("args", [])
        if firefox_args:
            for arg in firefox_args:
                if arg not in opts.arguments:
                    opts.add_argument(arg)

        firefox_prefs = additional_firefox_opts.get("prefs", {})
        for pref, value in firefox_prefs.items():
            if pref not in opts.arguments:
                opts.set_preference(pref, value)

        for key, value in firefox_options.items():
            opts.set_capability(key, value)
        if "proxy_url" in browser_conf:
            opts.set_capability(
                "proxy",
                {
                    "proxyType": "manual",
                    "httpProxy": browser_conf["proxy_url"],
                    "sslProxy": browser_conf["proxy_url"],
                },
            )
        return opts

    @classmethod
    def from_conf(cls, browser_conf: dict) -> BrowserManager:
        browser_conf = copy(browser_conf)
        browser_conf = _remove_deprecated_items(browser_conf)

        log.debug(browser_conf)
        webdriver_name = browser_conf.get("webdriver", "Chrome").title()
        webdriver_class = getattr(webdriver, webdriver_name)

        if webdriver_class not in TRUSTED_WEB_DRIVERS:
            log.warning(f"Untrusted webdriver {webdriver_name}, may cause failure.")

        webdriver_kwargs = browser_conf.get("webdriver_options", {})
        browser_name = _get_browser_name(webdriver_kwargs, webdriver_name)

        if "proxy_url" in browser_conf:
            parsed_url = urlparse(browser_conf["proxy_url"])
            proxy_netloc = parsed_url.netloc or parsed_url.path
            browser_conf["proxy_url"] = proxy_netloc
        if browser_name == "chrome":
            opts = cls._config_options_for_chrome(browser_conf)
            if webdriver_class == webdriver.Remote:
                opts.add_argument("--no-sandbox")
            webdriver_kwargs["options"] = opts
        if browser_name == "firefox":
            webdriver_kwargs["options"] = cls._config_options_for_firefox(browser_conf)

        if webdriver_class in TRUSTED_WEB_DRIVERS and "command_executor" in browser_conf:
            webdriver_kwargs["command_executor"] = browser_conf["command_executor"]
        return cls(BrowserFactory(webdriver_class, webdriver_kwargs))

    @property
    def is_alive(self) -> bool:
        log.debug("alive check")
        if self.browser is None:
            return False
        try:
            self.browser.current_url
        except UnexpectedAlertPresentException:
            # We shouldn't think that an Unexpected alert means the browser is dead
            return True
        except Exception:
            log.exception("browser in unknown state, considering dead")
            return False
        return True

    def ensure_open(self) -> WebDriver:
        if self.is_alive:
            # typeguard as is_alive will not communicate as type guard
            assert self.browser is not None
            return self.browser
        else:
            return self.start()

    def add_cleanup(self, callback: Callable) -> None:
        assert self.browser is not None
        try:
            cl = self.browser.__cleanup  # type: ignore
        except AttributeError:
            cl = self.browser.__cleanup = []  # type: ignore
        cl.append(callback)

    def _consume_cleanups(self) -> None:
        try:
            cl = self.browser.__cleanup  # type: ignore
        except AttributeError:
            pass
        else:
            while cl:
                cl.pop()()

    def close(self) -> None:
        self._consume_cleanups()
        try:
            self.browser_factory.close(self.browser)
        except Exception as e:
            log.error("An exception happened during browser shutdown:")
            log.exception(e)
        finally:
            self.browser = None

    quit = close

    def start(self) -> WebDriver:
        if self.browser is not None:
            self.quit()
        return self.open_fresh()

    def open_fresh(self) -> WebDriver:
        log.info("starting browser")
        assert self.browser is None

        self.browser = self.browser_factory.create()
        return self.browser
