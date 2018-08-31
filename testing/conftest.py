import contextlib

import pytest
from wait_for import wait_for

WHARF_URL = "http://localhost:4899"
WHARF_IMAGE = "cfmeqe/webdriver-wharf"
BROWSER_IMAGE = "cfmeqe/cfme_sel_stable"


@contextlib.contextmanager
def crate_or_reuse_existing(name, image, **kw):
    import docker

    client = docker.from_env(version="auto")
    client.images.pull(image)

    try:
        # assume similar setup
        container = client.containers.get(name)
        existed = True
    except docker.errors.NotFound:
        container = client.containers.run(name=name, image=image, **kw)
        existed = False
    else:
        if container.status != "running":
            container.restart()
            existed = False
    yield container
    if not existed:
        container.kill()


@contextlib.contextmanager
def wharf_setup():
    from webdriver_kaifuku import wharf

    with crate_or_reuse_existing(
        name="webdriver-wharf-kaifuku-test",
        image="cfmeqe/webdriver-wharf",
        auto_remove=True,
        detach=True,
        privileged=True,
        network_mode="host",
        volumes={
            "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}
        },
    ):
        wc = wharf.Wharf(WHARF_URL)
        wait_for(wc.accepts_requests, timeout="20s", logger=wharf.log)

        yield {
            "webdriver_wharf": WHARF_URL,
            "webdriver": "Remote",
            "webdriver_options": {"desired_capabilities": {"browserName": "firefox"}},
        }


@contextlib.contextmanager
def docker_setup():
    with crate_or_reuse_existing(
        name="webdriver-kaifuku-test-browser",
        image=BROWSER_IMAGE,
        auto_remove=True,
        detach=True,
        privileged=True,
        publish_all_ports=True,
    ) as container:

        ports = container.attrs[u"NetworkSettings"][u"Ports"][u"4444/tcp"][0]
        url = "http://localhost:{port}/wd/hub".format(port=ports[u"HostPort"])
        yield {
            "webdriver": "Remote",
            "webdriver_options": {
                "desired_capabilities": {"browserName": "firefox"},
                "command_executor": url,
            },
        }


@contextlib.contextmanager
def plain_setup():
    pytest.xfail(
        "local browsers are not supported "
        "until we have a way to automate/ensure setup of webdrivers"
    )
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
