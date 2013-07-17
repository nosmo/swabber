import unittest
import datetime
import commands
import threading
import os
import tempfile
from swabber import BanEntry, createDB
from swabber import BanCleaner
from swabber import BanFetcher
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import zmq
from zmq.eventloop import ioloop, zmqstream

BAN_IP = "10.123.45.67"
DB_CONN = 'sqlite:///%s/swabber.db' % tempfile.mkdtemp()
BINDSTRING = "tcp://127.0.0.1:22620"

#Defining context outside to avoid attacker using up all FDs
context   = zmq.Context(1)

class Attacker(object): #(threading.Thread): 

    def __init__(self, testip): 
        self.testip = testip
        #threading.Thread.__init__(self)

    def start(self):
        socket    = context.socket(zmq.PUB)
        publisher = zmqstream.ZMQStream(socket)
        socket.connect(BINDSTRING)
        publisher.send_multipart(("swabber_bans", self.testip))
        publisher.close()
        socket.close(linger=0)
        #context.destroy(linger=0)
        return True

class StressTest(object): 

    def __init__(self, testip, hit_times=500000): 
        self.testip = testip
        self.hit_times = hit_times

    def run(self): 

        bfetcher = BanFetcher(DB_CONN, BINDSTRING, False)
        bfetcher.start()

        print "Starting attacks"

        for i in range(self.hit_times): 
            if i % 1000 == 0:
                print "Attacked %d times" % i

            a = Attacker(self.testip)
            a.start()
            del(a)

class BanTests(unittest.TestCase):

    def testBan(self):
        ban = BanEntry(BAN_IP, datetime.datetime.now())
        ban.ban()
        status, output = commands.getstatusoutput("/sbin/iptables -L -n")
        ban.unban()
        self.assertIn(BAN_IP, output, msg="IP address not banned")
        status, output = commands.getstatusoutput("/sbin/iptables -L -n")
        self.assertNotIn(BAN_IP, output, msg="IP address was not unbanned")

class CleanTests(unittest.TestCase): 
    
    def testClean(self): 
        db_conn = 'sqlite:///%s/swabber.db' % tempfile.mkdtemp()
        createDB(db_conn)

        engine = create_engine(db_conn, echo=False)
        Sessionmaker = sessionmaker(bind=engine)
        session = Sessionmaker()

        ban_len = 1
        bantime = datetime.timedelta(minutes=(ban_len*2))
        ban = BanEntry(BAN_IP, datetime.datetime.now() - bantime)
        session.add(ban)
        session.commit()

        ban.ban()
        cleaner = BanCleaner(db_conn, ban_len)
        cleaner.cleanBans()
        
        status, output = commands.getstatusoutput("/sbin/iptables -L -n")
        self.assertNotIn(BAN_IP, output, msg="Ban was not reset by cleaner")

def main():
    if os.getuid() != 0: 
        print "Tests must be run as root"
        raise SystemExit
    else:
        s = StressTest(BAN_IP)
        s.run()
        unittest.main()

if __name__ == '__main__':
    main()

