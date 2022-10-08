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
    Extract the name of the browser from the desired capabilities
    """
    name = (
        webdriver_kwargs.get("desired_capabilities", {}).get("browserName")
        if webdriver_name.lower() == "remote"
        else webdriver_name
    )

    if name:
        return name.lower()
    raise ValueError("No browser name specified")


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
    def _config_options_for_remote_chrome(browser_conf: dict) -> webdriver.ChromeOptions:
        opts = webdriver.ChromeOptions()
        desired_capabilities = browser_conf.get("webdriver_options", {}).get(
            "desired_capabilities", {}
        )
        desired_capabilities_chrome_options = desired_capabilities.pop("chromeOptions", {})
        chrome_args = desired_capabilities_chrome_options.get("args", [])
        if chrome_args is not None:
            for arg in chrome_args:
                if arg not in opts.arguments:
                    opts.add_argument(arg)
        opts.add_argument("--no-sandbox")
        if "proxy_url" in browser_conf:
            opts.add_argument(f"--proxy-server={browser_conf['proxy_url']}")
        for key, value in desired_capabilities.items():
            opts.set_capability(key, value)
        return opts

    @staticmethod
    def _config_options_for_remote_firefox(browser_conf: dict) -> webdriver.FirefoxOptions:
        opts = webdriver.FirefoxOptions()
        desired_capabilities = browser_conf.get("webdriver_options", {}).get(
            "desired_capabilities", {}
        )
        desired_capabilities_firefox_options = desired_capabilities.get("firefoxOptions", {})
        firefox_prefs = desired_capabilities_firefox_options.get("prefs", {})
        for pref, value in firefox_prefs.items():
            if pref not in opts.arguments:
                opts.set_preference(pref, value)

        firefox_args = desired_capabilities_firefox_options.get("args", [])
        if firefox_args is not None:
            for arg in firefox_args:
                if arg not in opts.arguments:
                    opts.add_argument(arg)

        for key, value in desired_capabilities.items():
            if key == "firefoxOptions":
                opts.set_capability(key, value)
            else:
                opts.set_capability(key, value)
        if "proxy_url" in browser_conf:
            opts.set_capability(
                "proxy",
                {
                    "proxyType": "MANUAL",
                    "httpProxy": browser_conf["proxy_url"],
                    "sslProxy": browser_conf["proxy_url"],
                },
            )
        return opts

    @classmethod
    def from_conf(cls, browser_conf: dict) -> BrowserManager:
        browser_conf = copy(browser_conf)
        log.debug(browser_conf)
        webdriver_name = browser_conf.get("webdriver", "Firefox").title()
        webdriver_class = getattr(webdriver, webdriver_name)

        if webdriver_class not in TRUSTED_WEB_DRIVERS:
            log.warning(f"Untrusted webdriver {webdriver_name}, may cause failure.")

        webdriver_kwargs = browser_conf.get("webdriver_options", {})
        browser_name = _get_browser_name(webdriver_kwargs, webdriver_name)

        if "proxy_url" in browser_conf:
            parsed_url = urlparse(browser_conf["proxy_url"])
            proxy_netloc = parsed_url.netloc or parsed_url.path
            browser_conf["proxy_url"] = proxy_netloc
        if browser_name == "chrome" and webdriver_class == webdriver.Remote:
            webdriver_kwargs["options"] = cls._config_options_for_remote_chrome(browser_conf)
        if browser_name == "firefox" and webdriver_class == webdriver.Remote:
            webdriver_kwargs["options"] = cls._config_options_for_remote_firefox(browser_conf)

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
