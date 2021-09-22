<h1 align="center"> webdriver_kaifuku </h1>
<h3 align="center"> Restartable webdriver instances </h3>

<p align="center">
    <a href="https://pypi.org/project/webdriver-kaifuku/">
    <img alt="Python Versions" src="https://img.shields.io/pypi/pyversions/webdriver-kaifuku.svg?style=flat">
    </a>
    <a href="https://pypi.org/project/webdriver_kaifuku/#history">
    <img alt="PyPI version" src="https://badge.fury.io/py/webdriver-kaifuku.svg">
    </a>
    <a href="https://codecov.io/gh/RedHatQE/webdriver_kaifuku">
      <img src="https://codecov.io/gh/RonnyPfannschmidt/webdriver_kaifuku/branch/master/graph/badge.svg" />
    </a>
    <a href="https://github.com/RonnyPfannschmidt/webdriver_kaifuku/actions/workflows/test_suite.yml">
    <img alt="github actions" src="https://github.com/RonnyPfannschmidt/webdriver_kaifuku/actions/workflows/test_suite.yml/badge.svg">
    </a>
    <a href="https://github.com/RonnyPfannschmidt/webdriver_kaifuku/blob/master/LICENSE">
    <img alt="License" src="https://img.shields.io/pypi/l/webdriver_kaifuku.svg?version=latest">
    </a>
</p>
The library provides restartable webdriver instances.

### Usage:
It support both `local` and `remote` webdriver. Some basic examples are-

- Local Browser

Make sure `webdriver` is already installed on your local machine.
```python
from webdriver_kaifuku import BrowserManager

manager = BrowserManager.from_conf({"webdriver": "Chrome"})
manager.start()
manager.close()
```
- [Selenium Container](https://github.com/RedHatQE/selenium-images)

```python
from webdriver_kaifuku import BrowserManager

manager_config = {
    "webdriver": "Remote",
    "webdriver_options": {
        "desired_capabilities": {"browserName": "firefox"},
        "command_executor": "http://localhost:<port>/wd/hub",
    },
}
manager = BrowserManager.from_conf(manager_config)
manager.start()
manager.close()
```

- [Wharf](https://github.com/RedHatQE/webdriver-wharf)

```python
from webdriver_kaifuku import BrowserManager

manager_config = {
    "webdriver_wharf": "<wharf_url>",
    "webdriver": "Remote",
    "webdriver_options": {"desired_capabilities": {"browserName": "firefox"}},
}
manager = BrowserManager.from_conf(manager_config)
manager.start()
manager.close()
```
