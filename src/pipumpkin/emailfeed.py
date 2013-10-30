"""
Module for the TwitterFeedMonitor class.
"""
from datetime import datetime, timedelta
import dateutil.parser
import email
from email.mime.text import MIMEText
import imaplib
import logging
import Queue
import re
import smtplib
import socket
import time
import threading
import traceback

class EmailFeed(threading.Thread):
    """
    Look at messages sent to the given mailbox mentioning the current user,
    and add them to the queue. Intended to run as a separate thread.
    
    :param config: A `dict` of configuration data for the mail servers.
    
    This classes parses the plaintext contents of e-mails sent to the given
    address found in the given folder. Some extra arguments for text-to-speech
    conversion can be passed as strings in the e-mail itself, e.g. "rate:100",
    "volume:0.5", "voice:german". Only supports SSL IMAP and SMTP connections on
    default ports with the same username/password combination (feel free to
    customise). Works well with Gmail.
    """
    def __init__(self, config):
        """
        """
        threading.Thread.__init__(self)
        self.log = logging.getLogger("pipumpkin")

        # Keep track of all the sentences to be said in a priority queue, with
        # elements tuples of the form (scheduled_at, message, flags).
        self.queue = Queue.PriorityQueue()
        
        # A queue of email messages (see email module) to send.
        self.send_queue = Queue.Queue()
        
        # Delay between two IMAP searches.
        self.imap_poll_delay = timedelta(seconds=1)
        
        # Set to True to stop this thread gracefully.
        self.stop = False
        
        # Subject line of heartbeat e-mails.
        self.heartbeat_subject = "pipumpkin heartbeat"
        
        # Map a time code letter to an argument name for timedelta.
        self.time_code_map = {"s": "seconds", "m": "minutes", "h": "hours"}
        
        # Read config
        self.user = config["user"]
        self.password = config["password"]
        self.imap_server = config["imap-server"]
        self.smtp_server = config["smtp-server"]
        self.mailbox = config["imap-mailbox"]
            
    def run(self):
        """Should be invoked by self.start() in a different thread
        
        * Looks for unread emails
        * Parses emails and put their contents in the submission queue
        * Sends messages on the send queue.
        """
        self.last_imap_search = datetime.now()
        
        # Try reconnecting if a socket error occurs (connection lost, etc)
        while not self.stop:
            try:
                self.imap = self._connect_imap()
                self.log.info("Connected, looking for unread messages in {0}"
                    .format(self.mailbox))
                while not self.stop:
                    self.loop()
            except (socket.error, imaplib.IMAP4_SSL.error,
                    smtplib.SMTPException):
                e_str = traceback.format_exc()
                self.log.error("An error occurred:\n{0}".format(e_str))
                # Don't try to reconnect too often
                time.sleep(self.imap_poll_delay.seconds)
    
    def _connect_imap(self):
        """Connect to the specified IMAP server using SSL
        """
        self.log.info("Connecting to IMAP server {0}".format(self.imap_server))
        imap = imaplib.IMAP4_SSL(self.imap_server)
        imap.login(self.user, self.password)
        return imap
                                                                
    def _connect_smtp(self):
        """Connect to the specified SMTP server using SSL
        """
        self.log.info("Connecting to SMTP server {0}".format(self.smtp_server))
        smtp = smtplib.SMTP_SSL(self.smtp_server)
        smtp.login(self.user, self.password)
        return smtp
    
    def loop(self):
        """Main thread loop: check for mentions to speak
        """
        # Limit CPU time taken by this thread
        time.sleep(0.1)
        
        # Send messages from the send_queue to the current user
        messages = []    
        while self.send_queue.qsize():
            try:
                messages.append(self.send_queue.get(block=False))
            except Queue.Empty:
                break
        if messages:
            smtp = self._connect_smtp()
            for message in messages:
                self.log.info("Sending: {0}".format(message.get_payload()))
                smtp.sendmail(self.user, [self.user], message.as_string())
            smtp.quit()

        # Limit the rate of IMAP queries (be nice with the server)
        now = datetime.now()
        if now - self.last_imap_search > self.imap_poll_delay:
            self.last_imap_search = now
        else:
            return
            
        # Look for unread messages
        self.imap.select(self.mailbox)
        typ, unseen = self.imap.search(None, "(UNSEEN)")
        if typ != "OK":
            self.log.error("Imap search returned {0}".format(typ))
            return
        unseen = unseen[0].split()
        if not unseen:
            return
        
        # Parse them
        self.log.info("{0} unread messages found".format(len(unseen)))
        for num in unseen:
            typ, data = self.imap.fetch(num, "(RFC822)")
            if typ != "OK":
                self.log.error("Imap fetch returned {0}".format(typ))
                return
            data_str = data[0][1]
            message = email.message_from_string(data_str)
            self.parse_email(message)
    
    def _get_plain_text(self, message):
        """Get text/plain parts in a message and add them together to form a
        whole sentence (usually there'll only be one).
        """
        result = []
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                # Note: call decode on the returned string to convert the result
                # to unicode (error handling scheme is "ignore" to avoid raising
                # exceptions). pyttsx seems to hang on invalid ascii characters!
                text = part.get_payload(decode=True).\
                    decode(part.get_content_charset(), "ignore")
                result.append(text.strip())
        
        return "".join(result)

    def parse_email(self, message):
        """Look for the sentence to speak in the e-mail. Parse some arguments for
        reply.
        """
        # In case you're putting all pipumpkin-related mails into the same
        # folder - don't process heartbeats and queue acknowledgments.
        if message["Subject"] == self.heartbeat_subject:
            self.log.info("Skipped heartbeat mail.")
            return
            
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
        flags = re.findall("(\w+):(\S+)", text)
        flags = dict((str(k.lower()), v) for k, v in flags)
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
                # Give some feedback that the delay wasn't accepted
                flags["delay"] = "?"
            else:
                scheduled_at = scheduled_at + delay
                flags["delay"] = "{0} {1}".format(value, key)
                
        # Make a nice string representation of flags for the reply
        flags_str = ", ".join("{0}={1}".format(k, v)
                              for k, v in flags.iteritems())
        
        # Not all characters can be converted back from unicode to ascii. Take
        # that into account when printing logs.
        safe_text = text.encode(errors='replace')
        self.log.info("Queued for {0}: '{1}'".format(scheduled_at, safe_text))
        self.queue.put((scheduled_at, text, flags))
        
    def send_heartbeat(self, contents):
        """Send an e-mail to the specified address with the subject
        "pipumpkin heartbeat" containing some useful information.
        
        :param contents: some plaintext contents for the heartbeat e-mail.
        """
        msg = MIMEText(contents)
        msg["Subject"] = self.heartbeat_subject
        msg["From"] = self.user
        msg["To"] = self.user
        self.send_queue.put(msg)
        
