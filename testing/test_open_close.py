import pytest


@pytest.fixture
def manager():
    pass


def test_open_close(manager):
    driver = manager.open()
    driver2 = manager.open()
    assert driver is driver2
