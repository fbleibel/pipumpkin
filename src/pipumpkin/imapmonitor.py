"""
Module for the TwitterFeedMonitor class.
"""
import base64
from datetime import datetime, timedelta
import dateutil.parser
import email
import imaplib
import json
import logging
import Queue
import re
import socket
import time
import threading

IMAP_CONFIG = "/etc/pipumpkin-imap-config"

class IMAPMonitor(threading.Thread):
    """
    Look at messages sent to the given mailbox mentioning the current user,
    and add them to the queue.
    
    :param sentence_queue: the parsed sentences to speak will be put in this
        queue.
    :param reply_queue: Place elements in this queue to reply to twitter
        messages.
    """
    def __init__(self, sentence_queue):
        """
        """
        threading.Thread.__init__(self)
        self.log = logging.getLogger("pipumpkin")
        self.sentence_queue = sentence_queue
        self.poll_delay = timedelta(seconds=2)
        # Set to True to stop this thread gracefully.
        self.stop = False
        # Map a time code letter to an argument name for timedelta.
        self.time_code_map = {"s": "seconds", "m": "minutes", "h": "hours"}
        with open(IMAP_CONFIG, "r") as file:
            imap_config = json.load(file)
        self.user = imap_config["user"]
        self.password = imap_config["password"]
        self.server = imap_config["server"]
        self.mailbox = imap_config["mailbox"]
            
    def run(self):
        """Should be invoked by self.start() in a different thread
        
        * Looks for unread emails
        * Sends elements added to the reply queue.
        """
        # Try reconnecting if a socket error occurs (connection lost, etc)
        while not self.stop:
            try:
                self._connect_imap()
                while not self.stop:
                    self.loop()
            except (socket.error, imaplib.IMAP4_SSL.error), e:
                self.log.error("An error occurred: {0}".format(e))
                # Don't try to reconnect too often
                time.sleep(self.poll_delay.seconds)
    
    def _connect_imap(self):
        """Connect to the specified imap server
        """
        self.log.info("Connecting to IMAP server {0}".format(self.server))
        self.imap = imaplib.IMAP4_SSL(self.server)
        self.imap.login(self.user, self.password)
        self.log.info("Connected, looking for unread messages in {0}".format(
                                                                self.mailbox))
    
    def loop(self):
        """Main thread loop: check for mentions to speak, check for replies to
        send.
        """
        self.imap.select(self.mailbox)
        typ, unseen = self.imap.search(None, "(UNSEEN)")
        if typ != "OK":
            self.log.error("Imap search returned {0}".format(typ))
            return
        unseen = unseen[0].split()
        if not unseen:
            return
        self.log.info("{0} unread messages found".format(len(unseen)))
        for num in unseen:
            typ, data = self.imap.fetch(num, "(RFC822)")
            if typ != "OK":
                self.log.error("Imap fetch returned {0}".format(typ))
                return
            data_str = data[0][1]
            message = email.message_from_string(data_str)
            self.parse_email(message)
        
        # Limit the rate of imap queries
        time.sleep(self.poll_delay.seconds)
    
    def _get_plain_text(self, message):
        """Get text/plain parts in a message and add them together to form a
        whole sentence (usually there'll only be one) 
        """
        result = ""
        if message.get_content_type() == "text/plain":
            text = message.get_payload()
            encoding = message.get("Content-Transfer-Encoding")
            if encoding and encoding.lower() == "base64":
                text = base64.decodestring(text)
            result = text.strip()
    
        if message.is_multipart():
            for part in message.get_payload():
                result += self._get_plain_text(part)
    
        return result

    def parse_email(self, message):
        """Look for the sentence to speak in the e-mail. Parse some arguments for
        reply.
        """
        self.log.info("Parsing message {0[Subject]} from {0[From]}".format(
                                                                    message))
        text = self._get_plain_text(message)
        if not text:
            self.log.warning("Message was empty!")
            return
        
        scheduled_at = datetime.now()
        if "Date" in message:
            scheduled_at = dateutil.parser.parse(message["Date"])
        # Convert back to a naive, non-timezone-aware date, assuming it was in
        # local time to begin with.
        scheduled_at = scheduled_at.replace(tzinfo=None)
        
        # Parse for embedded arguments (convert keys to lowercase)
        flags = dict(map(str.lower, re.findall("(\w+):(\S+)", text)))
        # And remove the arguments found from the text
        text = re.sub("(\w+):(\S+)", "", text)
        
        if "delay" in flags:
            delay = None
            # Delay the scheduled speech time
            # Delay can be expressed in seconds, minutes or hours, e.g.
            # "5s", "2m", or "1h"
            match = re.match("(\d+)(\w)", flags["delay"])
            if match:
                value, time_code = match.groups()
                try:
                    value = float(value)
                except ValueError:
                    pass
                else:
                    if time_code in self.time_code_map:
                        key = self.time_code_map[time_code]
                        delay = timedelta(**{key: value})
            if delay is None:
                # Give some user feedback that the delay wasn't accepted
                flags["delay"] = "?"
            else:
                scheduled_at = scheduled_at + delay
                flags["delay"] = "{0} {1}".format(value, key)
                
        # Make a nice string representation of flags for the reply
        flags_str = ", ".join("{0}={1}".format(k, v)
                              for k, v in flags.iteritems())
        
        self.log.info("Queued for {0}: '{1}'".format(scheduled_at, text))
        self.sentence_queue.put((scheduled_at, text, flags))
    
