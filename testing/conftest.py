import contextlib

import pytest


@contextlib.contextmanager
def wharf_setup():
    import docker

    client = docker.from_env(version="auto")
    client.images.pull("cfmeqe/webdriver-wharf")
    client.images.pull("cfmeqe/cfme_sel_stable")
    container = client.containers.run(
        name="webdriver-wharf-kaifuku-test",
        image="cfmeqe/webdriver-wharf",
        auto_remove=True,
        detach=True,
        privileged=True,
        network_mode="host",
        volumes={
            "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}
        },
    )
    yield {
        "webdriver_wharf": "http://localhost:4899",
        "webdriver": "Remote",
        "webdriver_options": {"desired_capabilities": {"browserName": "firefox"}},
    }
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
