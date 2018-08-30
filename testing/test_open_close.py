def test_open_close(manager):
    driver = manager.start()
    driver2 = manager.start()
    assert driver is driver2
