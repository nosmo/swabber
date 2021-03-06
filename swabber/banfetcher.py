#!/usr/bin/env python

__author__ = "nosmo@nosmo.me"

import json
import zmq
from zmq.eventloop import ioloop, zmqstream

import datetime
import logging
import re
import sys
import threading

import banobjects

BINDSTRINGS = ["tcp://127.0.0.1:22620"]

class BanFetcher(threading.Thread):

    def subscription(self, message):
        if len(message) != 2:
            logging.debug("ZMQ received invalid message: %s", message)
            return False

        action, ipaddress = message

        ipaddress= ipaddress.strip()
        ipmatch = re.compile("^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        if not ipmatch.match(ipaddress):
            logging.error("Failed to validate IP address %s - rejecting", ipaddress)
            return False

        if action == "swabber_bans":
            logging.debug("Received ban for %s", message[1])
            thenow = datetime.datetime.now()

            with self.iptables_lock:
                ban = self.BanObject(ipaddress)
                logging.debug("Created banentry for %s", ipaddress)

                logging.debug("Fetcher got iptables lock")
                try:
                    if ban.banstart:
                        logging.info("Created ban for %s at %s", ipaddress, thenow)
                        ban.unban(self.interface)
                        ban.ban(self.interface)
                    else:
                        ban.ban(self.interface)
                        logging.info("Extended ban for %s", ipaddress)

                except self.BanObject.fault_exception as e:
                    logging.error("Failed to initialise ban - do we lack permissions?: %s", e)
                    #raise SystemExit

        else:
            logging.error("Got an invalid message header: %s", message)


    #TODO make lock optional
    def __init__(self, bindstrings,
                 interface, backend,
                 lock):
        self.bindstrings = bindstrings
        self.interface = interface
        self.backend = backend
        self.BanObject = banobjects.entries[backend]

        self.sockets = {}

        for bindstring in bindstrings:

            context = zmq.Context()
            self.sockets[bindstring] = context.socket(zmq.SUB)
            subscriber = zmqstream.ZMQStream(self.sockets[bindstring])

            if "RCVHWM" in dir(zmq):
                self.sockets[bindstring].setsockopt(zmq.RCVHWM, 2000)
            if "SNDHWM" in dir(zmq):
                self.sockets[bindstring].setsockopt(zmq.SNDHWM, 2000)
            if "HWM" in dir(zmq):
                self.sockets[bindstring].setsockopt(zmq.HWM, 2000)

            # SWAP is removed in zmq :(
            if "SWAP" in dir(zmq):
                self.sockets[bindstring].setsockopt(zmq.SWAP, 200*2**10)

            self.sockets[bindstring].setsockopt(zmq.SUBSCRIBE, "swabber_bans")
            self.sockets[bindstring].connect(bindstring)
            subscriber.on_recv(self.subscription)

        self.iptables_lock = lock

        threading.Thread.__init__(self)


    def stopIt(self):
        self.loop.stop()

    def run(self):
        self.loop = ioloop.IOLoop.instance().start()

if __name__ == "__main__":

    verbose = False

    if verbose:
        mainlogger = logging.getLogger()

        logging.basicConfig(level=logging.DEBUG)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        mainlogger.addHandler(ch)

    bfetcher = BanFetcher( BINDSTRING, "eth+", "iptables", threading.Lock())
    bfetcher.run()
