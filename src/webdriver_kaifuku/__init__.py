"""Core functionality for starting, restarting, and stopping a selenium browser."""
import atexit
import logging
import warnings
from urllib.error import URLError
from urllib.parse import urlparse

import attr
from selenium import webdriver
from selenium.common.exceptions import (
    UnexpectedAlertPresentException,
    WebDriverException,
)
from selenium.webdriver.remote.file_detector import UselessFileDetector

from .tries import tries

log = logging.getLogger(__name__)


THIRTY_SECONDS = 30

BROWSER_ERRORS = URLError, WebDriverException
WHARF_OUTER_RETRIES = 2
TRUSTED_WEB_DRIVERS = [webdriver.Firefox, webdriver.Chrome, webdriver.Remote]


def _get_browser_name(browser_kwargs):
    """
    Extract the name of the browser from the desired capabilities
    """
    name = browser_kwargs.get("desired_capabilities", {}).get("browserName")
    if name:
        return name.lower()


def _populate_chrome_options(browser_kwargs):
    """
    Initialize the 'chromeOptions' within desired_capabilities.

    'chromeOptions' and 'args' are created as empty dict/lists if they are not present.

    Existing values will not be removed.
    """
    desired_capabilities = browser_kwargs.get("desired_capabilities", {})
    desired_capabilities["chromeOptions"] = desired_capabilities.get(
        "chromeOptions", {}
    )
    chrome_options = desired_capabilities["chromeOptions"]

    chrome_options["args"] = chrome_options.get("args", [])

    return browser_kwargs


@attr.s
class BrowserFactory(object):
    webdriver_class = attr.ib()
    browser_kwargs = attr.ib()

    def __attrs_post_init__(self):
        if self.webdriver_class is not webdriver.Remote:
            # desired_capabilities is only for Remote driver, but can sneak in
            self.browser_kwargs.pop("desired_capabilities", None)

    def processed_browser_args(self):
        if self.browser_kwargs.get("keep_alive_allowed"):
            # keep_alive_allowed is not a valid browser option,
            # it just enables the opt-in for keep-alive
            copy = dict(self.browser_kwargs)
            del copy["keep_alive_allowed"]
            return copy

        browser_kwargs = dict(self.browser_kwargs)
        browser_kwargs.pop("keep_alive_allowed", None)

        if "keep_alive" in browser_kwargs:
            warnings.warn(
                "forcing browser keep_alive to False due to selenium bugs\n"
                "we are aware of the performance cost and hope to redeem",
                category=RuntimeWarning,
            )
            return dict(browser_kwargs, keep_alive=False)
        return browser_kwargs

    def create(self):
        try:
            browser = tries(
                2,
                WebDriverException,
                self.webdriver_class,
                **self.processed_browser_args(),
            )
        except URLError as e:
            if e.reason.errno == 111:
                # Known issue
                raise RuntimeError(
                    "Could not connect to Selenium server. Is it up and running?"
                )
            else:
                # Unknown issue
                raise

        browser.file_detector = UselessFileDetector()
        browser.maximize_window()
        return browser

    def close(self, browser):
        if browser:
            browser.quit()


@attr.s
class WharfFactory(BrowserFactory):
    wharf = attr.ib()

    DEFAULT_WHARF_CHROME_OPT_ARGS = ["--no-sandbox"]

    def __attrs_post_init__(self):
        if _get_browser_name(self.browser_kwargs) == "chrome":
            # chrome uses containers to sandbox the browser, and we use containers to
            # run chrome in wharf, so disable the sandbox if running chrome in wharf
            co = self.browser_kwargs["desired_capabilities"].get("chromeOptions", {})
            for arg in self.DEFAULT_WHARF_CHROME_OPT_ARGS:
                if "args" not in co:
                    co["args"] = [arg]
                elif arg not in co["args"]:
                    co["args"].append(arg)
            self.browser_kwargs["desired_capabilities"]["chromeOptions"] = co
            _populate_chrome_options(self.browser_kwargs)
            self.browser_kwargs["desired_capabilities"]["chromeOptions"]["args"].append(
                "--no-sandbox"
            )

    def processed_browser_args(self):
        command_executor = self.wharf.config["webdriver_url"]
        view_msg = "tests can be viewed via vnc on display {}".format(
            self.wharf.config["vnc_display"]
        )
        log.info("webdriver command executor set to %s", command_executor)
        log.info(view_msg)
        return dict(
            super(WharfFactory, self).processed_browser_args(),
            command_executor=command_executor,
        )

    def create(self):
        def inner():
            try:
                self.wharf.checkout()
                return super(WharfFactory, self).create()
            except URLError as ex:
                # connection to selenium was refused for unknown reasons
                log.error(
                    "URLError connecting to selenium; recycling container. URLError:"
                )
                log.exception(ex)
                self.wharf.checkin()
                raise
            except Exception:
                log.exception("failure on webdriver usage, returning container")
                self.wharf.checkin()
                raise

        return tries(WHARF_OUTER_RETRIES, BROWSER_ERRORS, inner)

    def close(self, browser):
        try:
            super(WharfFactory, self).close(browser)
        finally:
            self.wharf.checkin()


@attr.s
class BrowserManager(object):
    BR_FACTORY_CLASS = BrowserFactory
    WF_FACTORY_CLASS = WharfFactory

    DEFAULT_CHROME_OPT_ARGS = ["--no-sandbox"]

    browser_factory = attr.ib()
    browser = attr.ib(default=None, init=False)

    @staticmethod
    def _config_kwargs_for_remote_chrome(browser_kwargs):
        _populate_chrome_options(browser_kwargs)
        browser_kwargs["desired_capabilities"]["chromeOptions"]["args"].append(
            "--no-sandbox"
        )
        browser_kwargs["desired_capabilities"].pop("marionette", None)

    @staticmethod
    def _config_kwargs_for_proxy(browser_kwargs, proxy_url):
        browser_name = _get_browser_name(browser_kwargs)

        parsed_url = urlparse(proxy_url)
        # proxy options don't need to include the scheme, just host:port
        proxy_netloc = parsed_url.netloc or parsed_url.path

        if browser_name == "chrome":
            _populate_chrome_options(browser_kwargs)
            if not parsed_url.scheme:
                parsed_url
            browser_kwargs["desired_capabilities"]["chromeOptions"]["args"].append(
                f"--proxy-server={proxy_netloc}"
            )

        elif browser_name == "firefox":
            browser_kwargs["desired_capabilities"] = browser_kwargs.get(
                "desired_capabilities", {}
            )
            browser_kwargs["desired_capabilities"]["proxy"] = {
                "proxyType": "MANUAL",
                "httpProxy": proxy_netloc,
                "sslProxy": proxy_netloc,
            }

        else:
            log.error(
                "ignoring proxy configuration for unknown browser type '%s'",
                browser_name,
            )

    @classmethod
    def from_conf(cls, browser_conf):
        log.debug(browser_conf)
        webdriver_name = browser_conf.get("webdriver", "Firefox").title()
        webdriver_class = getattr(webdriver, webdriver_name)

        if webdriver_class not in TRUSTED_WEB_DRIVERS:
            log.warning(f"Untrusted webdriver {webdriver_name}, may cause failure.")

        browser_kwargs = browser_conf.get("webdriver_options", {})

        if "proxy_url" in browser_conf:
            cls._config_kwargs_for_proxy(browser_kwargs, browser_conf["proxy_url"])

        if "webdriver_wharf" in browser_conf:
            log.warning("wharf")
            from .wharf import Wharf

            wharf = Wharf(browser_conf["webdriver_wharf"])
            atexit.register(wharf.checkin)
            return cls(cls.WF_FACTORY_CLASS(webdriver_class, browser_kwargs, wharf))
        else:
            if webdriver_class == webdriver.Remote:
                if _get_browser_name(browser_kwargs) == "chrome":
                    cls._config_kwargs_for_remote_chrome(browser_kwargs)
                if "command_executor" in browser_conf:
                    browser_kwargs["command_executor"] = browser_conf[
                        "command_executor"
                    ]

            return cls(cls.BR_FACTORY_CLASS(webdriver_class, browser_kwargs))

    @property
    def is_alive(self):
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

    def ensure_open(self):
        if self.is_alive:
            return self.browser
        else:
            return self.start()

    def add_cleanup(self, callback):
        assert self.browser is not None
        try:
            cl = self.browser.__cleanup
        except AttributeError:
            cl = self.browser.__cleanup = []
        cl.append(callback)

    def _consume_cleanups(self):
        try:
            cl = self.browser.__cleanup
        except AttributeError:
            pass
        else:
            while cl:
                cl.pop()()

    def close(self):
        self._consume_cleanups()
        try:
            self.browser_factory.close(self.browser)
        except Exception as e:
            log.error("An exception happened during browser shutdown:")
            log.exception(e)
        finally:
            self.browser = None

    quit = close

    def start(self):
        if self.browser is not None:
            self.quit()
        return self.open_fresh()

    def open_fresh(self):
        log.info("starting browser")
        assert self.browser is None

        self.browser = self.browser_factory.create()
        return self.browser
