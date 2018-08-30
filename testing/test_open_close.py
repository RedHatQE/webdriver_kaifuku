def test_open_close(manager):
    driver = manager.ensure_open()
    driver2 = manager.ensure_open()
    assert driver is driver2
    driver3 = manager.start()
    assert driver3 is not driver2
