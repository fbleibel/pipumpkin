"""
A talking pumpkin!
"""
from datetime import datetime, timedelta
import logging
import pyttsx
import Queue
import re
import subprocess
import time
import urllib2

from pipumpkin.tweeter import TweeterFeed
from pipumpkin.feedmonitor import TweeterFeedMonitor

class PiPumpkin(object):
    """
    Our main PiPupmkin instance. Call run() to start looking for tweets to
    speak. feed_monitor is the producer, adding words to the queue; 
    this class is the consumer.
    """
    def __init__(self):
        """
        """
        # Daemon configuration
        self.pidfile_path =  '/var/run/testdaemon/testdaemon.pid'
        self.pidfile_timeout = 5
        
        self.feed = TweeterFeed()
        self.log = logging.getLogger("pipumpkin")
        # Keep track of all the sentences to be said in a priority queue, with
        # elements tuples of the form (scheduled_at, message).
        self.sentence_queue = Queue.PriorityQueue()
        # The feed monitor can also send twitter replies as they are placed into
        # the reply queue. These are tuples (tweet_id, reply_contents).
        self.reply_queue = Queue.Queue()
        # Use a feed monitor which will be started as a separate thread.
        self.feed_monitor = TweeterFeedMonitor(self.feed,
                                               self.sentence_queue,
                                               self.reply_queue)
        self.speech_engine = pyttsx.init("espeak")
        
    def _get_ifconfig_addrs(self):
        """Returns the list of all ipv4 addresses found in "ifconfig"
        """
        process = subprocess.Popen("ifconfig", stdout=subprocess.PIPE)
        stdout, _ = process.communicate()
        process.wait()
        addrs = re.findall("inet addr:(\d+\.\d+\.\d+\.\d+)\s", stdout)
        return addrs
        
    def run(self):
        """Run in an infinite loop - this process will usually be killed with
        SIGKILL.
        """
        self.last_alive_message = datetime.now()
        self.speech_engine.startLoop(False)
        self.alive_timeout = timedelta(minutes=1)
        self.feed_monitor.start()
        # Later on, maybe we could be stop this program in a nicer fashion than
        # killing it?
        self.log.info("Initialisation complete, starting main loop")
        try:
            while True:
                self.loop()
                self.speech_engine.iterate()
        finally:
            self.feed_monitor.stop = True
            self.speech_engine.endLoop()
            self.feed_monitor.join()

    def loop(self):
        """Main application loop. Runs continuously.
        """
        now = datetime.now()
        
        # Send "alive" messages periodically
        if now - self.last_alive_message > self.alive_timeout:
            # Adjust the periodicity of "I'm alive" messages; if they are
            # sucessfully sent, use a longer timeout than otherwise.
            if self.send_alive():
                self.alive_timeout = timedelta(minutes=30)
            else:
                self.alive_timeout = timedelta(minutes=1)
            self.last_alive_message = now

        # Look for tweets to speak
        try:
            speak_at, text = self.sentence_queue.get(block=False)
            # Start speaking tweets if their scheduled time has passed
            
            if speak_at > now:
                # This tweet is scheduled into the future. Put it back into the
                # queue.
                self.sentence_queue.put(candidate)
            else:
                self.log.info("Speaking: {0}".format(text))
                self.speech_engine.say(text)
        except Queue.Empty:
            pass
        
    def send_alive(self):    
        """Send an "alive" message to the tweeter account.
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
        self.log.info("Tweet 'alive' status, success = %s" % retval)

