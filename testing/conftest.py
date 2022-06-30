import contextlib
import subprocess
from urllib.request import urlopen

import pytest
from wait_for import wait_for

BROWSER_IMAGE = "quay.io/redhatqe/selenium-standalone:latest"

CONFIGS = [
    pytest.param(
        {
            "webdriver": "Remote",
            "proxy_url": "http://example.com:8080",
            "webdriver_options": {
                "command_executor": "http://127.0.0.1:4444",
                "desired_capabilities": {
                    "browserName": "firefox",
                    "acceptInsecureCerts": True,
                    "firefoxOptions": {
                        "prefs": {
                            "privacy.trackingprotection.enabled": False,
                            "browser.contentblocking.enabled": False,
                            "browser.privatebrowsing.autostart": True,
                        },
                        "args": ['-private'],
                    },
                },
            },
        },
        id="remote-firefox",
    ),
    pytest.param(
        {
            "webdriver": "Remote",
            "proxy_url": "http://example.com:8080",
            "webdriver_options": {
                "command_executor": "http://127.0.0.1:4444",
                "desired_capabilities": {
                    "browserName": "chrome",
                    "acceptInsecureCerts": True,
                    "chromeOptions": {
                        "args": ["--disable-application-cache"],
                    },
                    "goog:loggingPrefs": {"browser": "INFO", "performance": "ALL"},
                },
            },
        },
        id="remote-chrome",
    ),
]


@pytest.fixture(scope="session")
def selenium_container():
    ps = subprocess.run(
        [
            "podman",
            "run",
            "--rm",
            "-d",
            "-p",
            "127.0.0.1:4444:4444",
            "--shm-size=2g",
            BROWSER_IMAGE,
        ],
        capture_output=True,
    )
    wait_for(lambda: urlopen("http://127.0.0.1:4444"), timeout=180, handle_exception=True)
    container_id = ps.stdout.decode("utf-8").strip()
    yield container_id
    subprocess.run(["podman", "kill", container_id], stdout=subprocess.DEVNULL)


@pytest.fixture(params=CONFIGS)
def test_data(selenium_container, request: pytest.FixtureRequest):
    from webdriver_kaifuku import BrowserManager, log

    mgr = BrowserManager.from_conf(request.param)  # type: ignore
    browser_name = request.param["webdriver_options"]["desired_capabilities"][  # type: ignore
        "browserName"
    ]
    log.warning(mgr)
    with contextlib.closing(mgr) as mgr:
        yield mgr, browser_name
