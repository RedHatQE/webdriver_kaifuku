from __future__ import annotations

import pytest
from webdriver_kaifuku import BrowserManager


CONFIGS = [
    pytest.param(
        {
            "webdriver": "firefox",
            "webdriver_options": {
                "desired_capabilities": {
                    "browserName": "firefox",
                    "acceptInsecureCerts": True,
                    "firefoxOptions": {
                        "prefs": {
                            "bar": False,
                        },
                        "args": ["foo"],
                    },
                },
            },
        },
        "firefox",
        id="firefox",
    ),
    pytest.param(
        {
            "webdriver": "chrome",
            "webdriver_options": {
                "desired_capabilities": {
                    "browserName": "chrome",
                    "acceptInsecureCerts": True,
                    "chromeOptions": {
                        "args": ["foo"],
                    },
                },
            },
        },
        "chrome",
        id="chrome",
    ),
]


@pytest.mark.parametrize("conf,browser_name", CONFIGS)
def test_initializing_from_config(conf: dict, browser_name: str):
    manager = BrowserManager.from_conf(conf)

    args = manager.browser_factory.processed_browser_args()
    options = args["options"]

    assert options.capabilities.get("acceptInsecureCerts") is True
    assert options.arguments == ["foo"]
    if browser_name == "firefox":
        assert options.preferences == {"bar": False}
