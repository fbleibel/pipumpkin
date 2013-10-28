"""
Module for the TwitterFeedMonitor class.
"""
from datetime import datetime, timedelta
import logging
import Queue
import re
import time
import threading
import tweepy

from pipumpkin.tweeter import FeedError

class TweeterFeedMonitor(threading.Thread):
    """
    Look at tweets mentioning the current user, and add them to the queue.
    Only tweets older than the date when the monitor thread was started will be
    taken into account.
    
    :param feed: An instance of a `TwitterFeed` object.
    :param sentence_queue: the parsed sentences to speak will be put in this
        queue.
    :param reply_queue: Place elements in this queue to reply to twitter
        messages.
    """
    def __init__(self, feed, sentence_queue, reply_queue):
        """
        """
        threading.Thread.__init__(self)
        self.log = logging.getLogger("pipumpkin")
        self.feed = feed
        self.sentence_queue = sentence_queue
        self.reply_queue = reply_queue
        # Space out the twitter API calls
        self.mention_check_delay = timedelta(seconds=10)
        # The id of the latest mention found.
        self.last_mention_id = None
        # Set to True to stop this thread gracefully.
        self.stop = False
        
    def run(self):
        """Should be invoked by self.start() in a different thread
        
        * Looks for new mentions on the twitter timeline and parse them;
        * Sends elements added to the reply queue.
        """
        self.last_mention_check_time = datetime.now()

        # We may hit twitter API rate limiting, but keep trying.
        found_last_mention = False
        while not found_last_mention:
            try:
                self.last_mention_id = self.feed.get_latest_mention_id()
                found_last_mention = True
            except FeedError:
                time.sleep(10)
        
        log.info("Listening for tweets")
        while not self.stop:
            self.loop()
    
    def loop(self):
        """Main thread loop
        """
        now = datetime.now()
        # Limit the twitter API calls
        if now - self.last_mention_check_time > self.mention_check_delay:
            self.check_for_mentions()
        self.check_for_replies()
    
    def check_for_replies(self, timeout=2):
        """Look for replies in the reply queue and send them.
        
        This function may wait at most 'timeout' seconds while trying to get
        replies.
        """
        try:
            reply = self.reply_queue.get(block=True, timeout=timeout)
        except Queue.Empty:
            return
        self.log.info("Sending reply: {0[1]}".format(reply))
        self.feed.post_reply(*reply)
        
    def check_for_mentions(self):
        """
        """
        try:
            new_mentions = self.feed.get_mentions_after(self.last_mention_id)
        except FeedError:
            # Probably hit twitter API's rate limiting
            return
        if not new_mentions:
            self.log.warning("Nothing found")
            return
            
        self.log.info("{0} new mention tweets found since {1}".format(
            len(new_mentions), self.last_mention_id))
        
        self.last_mention_id = new_mentions[0].id
        username = self.feed.get_screen_name()
        # Go through all mentions in chrononogical order
        for tweet in reversed(new_mentions):
            self.log.info("Tweet: {0.text}".format(tweet))
            # Mention tweets start with @username, remove that.
            text = re.sub(re.escape("@{0}".format(username)),
                          "",
                          tweet.text,
                          flags=re.IGNORECASE)
            
            self.log.info("Text: '{0}'".format(text.strip()))
            # Remove any extraneous whitespaces
            text = text.strip()
            # Add them to the queue
            self.sentence_queue.put((tweet.created_at, text))
            self.reply_queue.put((tweet.id, "Acknowledged."))
            
