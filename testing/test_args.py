import contextlib

import pytest
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_kaifuku import BrowserManager


@pytest.mark.parametrize(
    "conf,name",
    [
        (
            {
                "webdriver": "Remote",
                "webdriver_options": {
                    "desired_capabilities": {
                        "browserName": "firefox",
                    },
                },
            },
            "firefox",
        ),
        (
            {
                "webdriver": "Remote",
                "webdriver_options": {"options": ChromeOptions()},
            },
            "chrome",
        ),
    ],
)
def test_name(conf: dict, name: str):
    """Browser name is read correctly"""
    mgr = BrowserManager.from_conf(conf)
    with contextlib.closing(mgr) as mgr:
        browser = mgr.start()
        assert browser.name == name
