"""
A talking pumpkin!
"""
import re
import time
from datetime import datetime, timedela
import urllib2
import subprocess

from pipumpkin.tweeter import TweeterFeed

class PiPumpkin(object):
    """
    Our main PiPupmkin instance. Call main() to start looking for tweets to
    speak.
    """
    def __init__(self):
        """
        """
        self.feed = TweeterFeed()
        
    def _get_ifconfig_addrs(self):
        """Returns the list of all ipv4 addresses found in "ifconfig"
        """
        process = subprocess.Popen("ifconfig", stdout=subprocess.PIPE)
        stdout, _ = process.communicate()
        process.wait()
        addrs = re.findall("inet addr:(\d+\.\d+\.\d+\.\d+)\s", stdout)
        return addrs
        
    def main(self):
        """Run in an infinite loop - this process will usually be killed with
        SIGKILL.
        """
        self.last_alive_message = datetime.now()
        while True:
            self.loop()

    def loop(self):
        """Main application loop. Runs continuously.
        """
        now = datetime.now()
        if now - self.last_alive_message > timedelta(minutes=1):
            self.send_alive()
            self.last_alive_message = now
        
    def send_alive(self):    
        """Send alive messages every minute
        """
        # Find the IP of the raspberry pi as seen behind the current NAT
        try:
            public_ip = urllib2.urlopen('https://enabledns.com/ip').read()
        except:
            public_ip = "Unknown"
        addrs = self._get_ifconfig_addrs()
        addrs.append(public_ip)
        status = "Time: {0}, addresses: {1}".format(
            datetime.now(), ", ".join(addrs))
        retval = self.feed.tweet_alive(status)
        print "Tweet 'alive' status, success = %s" % retval

