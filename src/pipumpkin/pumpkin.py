"""
A talking pumpkin!
"""
from datetime import datetime, timedelta
import json
import logging
import pyttsx
import Queue
import re
import subprocess
import time
import urllib2

EMAIL_CONFIG_FILE = "/etc/pipumpkin-email-config"

from pipumpkin.emailfeed import EmailFeed

class PiPumpkin(object):
    """
    Our main PiPupmkin instance. Call run() to start looking for text to
    speak. email_feed is the producer, adding words to the queue; 
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
        
        # Read configuration
        with open(EMAIL_CONFIG_FILE, "r") as file:
            self.config = json.load(file)
            
        # Send heartbeat messages regularly
        self.heartbeat_period = timedelta(minutes=30)
        
        # Valid properties accepted by pyttsx and a method to cast them from a
        # string.
        self.valid_properties = {"rate": int, "volume": float, "voice": str}
        
        # Use a feed monitor which will be started as a separate thread.
        self.email_feed = EmailFeed(self.config)

    def _get_ifconfig_addrs(self):
        """Returns the list of all ipv4 addresses found in "ifconfig".
        """
        process = subprocess.Popen("ifconfig", stdout=subprocess.PIPE)
        stdout, _ = process.communicate()
        process.wait()
        addrs = re.findall("inet addr:(\d+\.\d+\.\d+\.\d+)\s", stdout)
        return addrs
    
    def _create_speech_engine(self):
        """
        """
        # Create a new speech engine
        self.speech_engine = pyttsx.init()
        
        # Keep track of the number of utterances/sentences to know if we are
        # speaking. Unfortunatell engine.isBusy() is not reliable, see
        # https://github.com/parente/pyttsx/issues/13
        # This is to find out if we should run .iterate() as fast as possible.
        self.uttering = 0
        
        def incr_utter(_):
            self.uttering += 1
        def decr_utter(_, __):
            self.uttering -= 1
        self.speech_engine.connect("started-utterance", incr_utter)
        self.speech_engine.connect("finished-utterance", decr_utter)
        
    def run(self):
        """Run in an infinite loop - this process will usually be killed with
        SIGKILL.
        """
        self._create_speech_engine()
        
        # Remember default values for the engine properties.
        self.property_defaults = dict(
            (prop, self.speech_engine.getProperty(prop))
            for prop in self.valid_properties.iterkeys())
            
        # I find the default rate hard to understand with espeak...
        self.property_defaults["rate"] = 135

        # The default voice is None, fix this
        self.property_defaults["voice"] = "english"
        
        # Tell the world we're starting up
        self.email_feed.send_heartbeat("Ready to go! Will look for e-mails "
            "now. My IP addresses are {0}. Love, pipumpkin.".format(
            ", ".join(self._get_ifconfig_addrs())))
        self.last_heartbeat = datetime.now()
        
        # Start looking for e-mails in a separate thread
        self.email_feed.start()
        
        self.log.info("Initialisation complete, starting main loop")
        self.speech_engine.startLoop(False)
        
        try:
            # Note: you must kill (e.g. Ctrl+C) pipumpkin to terminate it.
            while True:
                # Can't rely on engine.isBusy() unfortunately
                if self.uttering == 0:
                    # Don't take too much processor time if we're not speaking                    
                    time.sleep(0.5)
                    self.loop()
                self.speech_engine.iterate()
        finally:
            self.email_feed.stop = True
            self.email_feed.join()
            self.speech_engine.endLoop()

    def loop(self):
        """Main application loop. Runs continuously. Take messages from the
        queue and speak them.
        """
        now = datetime.now()
        
        # Send regular heartbeat messages
        if now - self.last_heartbeat > self.heartbeat_period:
            self.email_feed.send_heartbeat("I am still alive! My IP addresses "
            "are {0}. Love, pipumpkin.".format(
            ", ".join(self._get_ifconfig_addrs())))
            self.last_heartbeat = now
        
        # Look for text to speak
        try:
            # (datetime, unicode, dict)
            speak_at, text, flags = self.email_feed.queue.get(block=False)
        except Queue.Empty:
            return
            
        # Start speaking entries if their scheduled time has passed
        if speak_at > now:
            # This sentence is scheduled into the future. Put it back into the
            # queue (there's no peek() method on PriorityQueue).
            self.email_feed.queue.put((speak_at, text, flags))
            return
            
        # Convert properties into valid pyttsx inputs
        pyttsx_flags = {}
        for key, value in flags.iteritems():
            cast = self.valid_properties.get(key)
            if not cast:
                # Discard unsupported properties
                continue
            # Transform the value from a string into the right datatype
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
        safe_text = text.encode(errors='replace')
        self.log.info("Speaking: {0}, flags={1}".format(safe_text, pyttsx_flags))
        self.speech_engine.say(text)
        
