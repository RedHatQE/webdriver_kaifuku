"""Core functionality for starting, restarting, and stopping a selenium browser."""
import atexit
import logging
import warnings
from urllib.error import URLError

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


@attr.s
class BrowserFactory(object):
    webdriver_class = attr.ib()
    browser_kwargs = attr.ib()

    def __attr_post_init__(self):
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
                **self.processed_browser_args()
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

    def __attr_post_init__(self):
        if (
            self.browser_kwargs.get("desired_capabilities", {}).get("browserName")
            == "chrome"
        ):
            # chrome uses containers to sandbox the browser, and we use containers to
            # run chrome in wharf, so disable the sandbox if running chrome in wharf
            co = self.browser_kwargs["desired_capabilities"].get("chromeOptions", {})
            arg = "--no-sandbox"
            if "args" not in co:
                co["args"] = [arg]
            elif arg not in co["args"]:
                co["args"].append(arg)
            self.browser_kwargs["desired_capabilities"]["chromeOptions"] = co

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
                # connection to selenum was refused for unknown reasons
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
    browser_factory = attr.ib()
    browser = attr.ib(default=None, init=False)

    @classmethod
    def from_conf(cls, browser_conf):
        log.debug(browser_conf)
        webdriver_name = browser_conf.get("webdriver", "Firefox")
        webdriver_class = getattr(webdriver, webdriver_name)

        browser_kwargs = browser_conf.get("webdriver_options", {})

        if "webdriver_wharf" in browser_conf:
            log.warning("wharf")
            from .wharf import Wharf

            wharf = Wharf(browser_conf["webdriver_wharf"])
            atexit.register(wharf.checkin)
            return cls(WharfFactory(webdriver_class, browser_kwargs, wharf))
        else:
            if webdriver_name == "Remote":
                if (
                    browser_conf["webdriver_options"]["desired_capabilities"][
                        "browserName"
                    ].lower()
                    == "chrome"
                ):
                    browser_kwargs["desired_capabilities"][
                        "chromeOptions"
                    ] = browser_conf["webdriver_options"]["desired_capabilities"].get(
                        "chromeOptions", {}
                    )
                    browser_kwargs["desired_capabilities"]["chromeOptions"][
                        "args"
                    ] = browser_kwargs["desired_capabilities"]["chromeOptions"].get(
                        "args", []
                    )
                    browser_kwargs["desired_capabilities"]["chromeOptions"][
                        "args"
                    ].append("--no-sandbox")
                    browser_kwargs["desired_capabilities"].pop("marionette", None)
                if "command_executor" in browser_conf:
                    browser_kwargs["command_executor"] = browser_conf[
                        "command_executor"
                    ]

            return cls(BrowserFactory(webdriver_class, browser_kwargs))

    def _is_alive(self):
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
        if self._is_alive():
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
