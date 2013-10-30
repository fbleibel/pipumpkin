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

from pipumpkin.imapmonitor import IMAPMonitor

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
        self.pidfile_path =  '/var/run/pipumpkin.pid'
        self.pidfile_timeout = 5
        self.stdin_path = '/dev/null'
        # There must be a better place to put these files...
        self.stdout_path = '/var/log/pipumpkin/stdout'
        self.stderr_path = '/var/log/pipumpkin/stderr'
        
        self.log = logging.getLogger("pipumpkin")
        
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
        # Valid properties accepted by pyttsx and a method to cast them from a
        # string
        self.valid_properties = {"rate": int, "volume": float, "voice": str}
        
        # Keep track of all the sentences to be said in a priority queue, with
        # elements tuples of the form (scheduled_at, message, flags).
        self.sentence_queue = Queue.PriorityQueue()
        # Use a feed monitor which will be started as a separate thread.
        self.feed_monitor = IMAPMonitor(self.sentence_queue)
        # Start up our speech engine
        self.speech_engine = pyttsx.init()
        # Remember default values for the engine properties.
        self.property_defaults = dict(
            (prop, self.speech_engine.getProperty(prop))
            for prop in self.valid_properties.iterkeys())
        # The default voice is None, fix this
        self.property_defaults["voice"] = "english"
        
        self.speech_engine.startLoop(False)
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
        """Main application loop. Runs continuously. Take messages from the
        queue and speak them.
        """
        # Look for tweets to speak
        try:
            speak_at, text, flags = self.sentence_queue.get(block=False)
        except Queue.Empty:
            return
            
        # Start speaking tweets if their scheduled time has passed
        if speak_at > now:
            # This tweet is scheduled into the future. Put it back into the
            # queue (there's no peek() method on PriorityQueue).
            self.sentence_queue.put((speak_at, text, flags))
            return
            
        # Convert properties into valid pyttsx inputs
        pyttsx_flags = {}
        for key, value in flags.iteritems():
            # Discard unsupported properties
            if key not in self.valid_properties:
                continue
            # Transform the value from a string into the right datatype
            cast = self.valid_properties[key]
            try:
                value = cast(value)
            except ValueError:
                continue
            pyttsx_flags[key] = value
        
        # Set properties for the next utterance
        for key, default in self.property_defaults.iteritems():
            value = pyttsx_flags.get(key, default)
            self.speech_engine.setProperty(key, value)
        
        # Say it!
        self.log.info("Speaking: {0}, flags={1}".format(text, pyttsx_flags))
        self.speech_engine.say(text)
