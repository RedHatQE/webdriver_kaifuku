import contextlib

import pytest
from wait_for import wait_for

WHARF_URL = "http://localhost:4899"


@contextlib.contextmanager
def wharf_setup():
    import docker
    from webdriver_kaifuku import wharf

    client = docker.from_env(version="auto")
    client.images.pull("cfmeqe/webdriver-wharf")
    client.images.pull("cfmeqe/cfme_sel_stable")
    preexisting_container = client.containers.get("webdriver-wharf-kaifuku-test")
    if preexisting_container is None:
        container = client.containers.run(
            name="webdriver-wharf-kaifuku-test",
            image="cfmeqe/webdriver-wharf",
            # auto_remove=True,
            detach=True,
            privileged=True,
            network_mode="host",
            volumes={
                "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}
            },
        )
    else:
        if preexisting_container.status != "running":
            preexisting_container.restart()
    wc = wharf.Wharf(WHARF_URL)
    wait_for(wc.accepts_requests, timeout="20s", logger=wharf.log)

    yield {
        "webdriver_wharf": WHARF_URL,
        "webdriver": "Remote",
        "webdriver_options": {"desired_capabilities": {"browserName": "firefox"}},
    }
    if preexisting_container is None:
        container.kill()


@contextlib.contextmanager
def docker_setup():
    yield {}


@contextlib.contextmanager
def plain_setup():
    yield {}


@pytest.fixture(scope="session", params=(wharf_setup, docker_setup, plain_setup))
def manager_config(request):
    with request.param() as data:
        yield data


@pytest.fixture
def manager(manager_config):
    from webdriver_kaifuku import BrowserManager, log

    mgr = BrowserManager.from_conf(manager_config)
    log.warning(mgr)
    with contextlib.closing(mgr) as mgr:
        yield mgr
