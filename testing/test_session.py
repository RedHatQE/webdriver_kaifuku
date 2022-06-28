from __future__ import annotations

import subprocess

import requests
from webdriver_kaifuku import BrowserManager


def test_open_close(test_data: tuple[BrowserManager, str]):
    manager, _ = test_data
    driver = manager.ensure_open()
    driver2 = manager.ensure_open()
    assert driver is driver2
    driver3 = manager.start()
    assert driver3 is not driver2


def test_session(test_data: tuple[BrowserManager, str], selenium_container: str):
    manager, browser_name = test_data
    driver = manager.ensure_open()
    r = requests.get("http://localhost:4444/status")
    assert r.ok
    assert driver.caps["acceptInsecureCerts"] is True
    assert driver.caps["browserName"] == browser_name
    if browser_name == "firefox":
        assert driver.caps["proxy"] == {
            "httpProxy": "example.com:8080",
            "proxyType": "MANUAL",
            "sslProxy": "example.com:8080",
        }
    if browser_name == "chrome":
        driver.caps["goog:loggingPrefs"] == {"browser": "INFO", "performance": "ALL"}
        ps = subprocess.run(
            [
                "podman",
                "exec",
                "-it",
                selenium_container,
                "bash",
                "-c",
                "for ps in $(ls /proc | grep -e [0-9]); do cat /proc/$ps/cmdline; echo; done",
            ],
            capture_output=True,
        )
        commands = ps.stdout.decode("utf-8").splitlines()
        chrome = [
            c
            for c in commands
            if "/opt/google/chrome/chrome" in c
            and "--no-sandbox" in c
            and "--proxy-server=example.com:8080" in c
        ]
        assert chrome
