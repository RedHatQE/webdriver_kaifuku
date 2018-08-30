"""Core functionality for starting, restarting, and stopping a selenium browser."""
import json
import logging
import os
import threading
import time

import requests

FIVE_MINUTES = 5 * 60
log = logging.getLogger(__name__)


class Wharf(object):
    # class level to allow python level atomic removal of instance values
    docker_id = None

    def __init__(self, wharf_url):
        self.wharf_url = wharf_url
        self._renew_thread = None

    def _get(self, *args):

        response = requests.get(os.path.join(self.wharf_url, *args))
        if response.status_code == 204:
            return
        try:
            return json.loads(response.content)
        except ValueError:
            raise ValueError("JSON could not be decoded:\n{}".format(response.content))

    def accepts_requests(self):
        try:
            self._get("status")
            return True
        except Exception:
            log.exception("error while checking %s", self)
            return False

    def checkout(self):
        if self.docker_id is not None:
            return self.docker_id
        checkout = self._get("checkout")
        self.docker_id, self.config = next(iter(checkout.items()))
        self._start_renew_thread()
        log.info("Checked out webdriver container %s", self.docker_id)
        log.debug("%r", checkout)
        return self.docker_id

    def checkin(self):
        # using dict pop to avoid race conditions
        my_id = self.__dict__.pop("docker_id", None)
        if my_id:
            self._get("checkin", my_id)
            log.info("Checked in webdriver container %s", my_id)
            self._renew_thread = None

    def _start_renew_thread(self):
        assert self._renew_thread is None
        self._renew_thread = threading.Thread(target=self._renew_function)
        self._renew_thread.daemon = True
        self._renew_thread.start()

    def _renew_function(self):
        # If we have a docker id, renew_timer shouldn't still be None
        log.debug("renew thread started")
        while True:
            time.sleep(FIVE_MINUTES)
            if self._renew_thread is not threading.current_thread():
                log.debug(
                    "renew done %s is not %s",
                    self._renew_thread,
                    threading.current_thread(),
                )
                return
            if self.docker_id is None:
                log.debug("renew done, docker id %s", self.docker_id)
                return
            expiry_info = self._get("renew", self.docker_id)
            self.config.update(expiry_info)
            log.info("Renewed webdriver container %s", self.docker_id)

    def __nonzero__(self):
        return self.docker_id is not None
