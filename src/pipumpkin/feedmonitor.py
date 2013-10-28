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
from pipumpkin import timezone

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
        # Space out the twitter API calls to avoid hitting rate limiting
        # This is slighty higher than 
        self.mention_check_delay = timedelta(seconds=65)
        # The id of the latest mention found.
        self.last_mention_id = None
        # Set to True to stop this thread gracefully.
        self.stop = False
        # Map a time code letter to an argument name for timedelta.
        self.time_code_map = {"s": "seconds", "m": "minutes", "h": "hours"}
            
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
                # Rate limiting means one call every minute is accepted
                time.sleep(self.mention_check_delay.seconds)
        
        self.log.info("Listening for tweets")
        while not self.stop:
            self.loop()
    
    def loop(self):
        """Main thread loop: check for mentions to speak, check for replies to
        send.
        """
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
        # Limit the rate of twitter API calls
        now = datetime.now()
        if now - self.last_mention_check_time < self.mention_check_delay:
            return
        self.last_mention_check_time = now
        
        try:
            new_mentions = self.feed.get_mentions_after(self.last_mention_id)
        except FeedError:
            # Probably hit twitter API's rate limiting
            return
            
        self.log.info("{0} new mention tweets found since {1}".format(
            len(new_mentions), self.last_mention_id))
            
        if not new_mentions:
            return
        
        self.last_mention_id = new_mentions[0].id
        
        # Go through all mentions in chrononogical order
        ignored = 0
        for tweet in reversed(new_mentions):
            if tweet.in_reply_to_status_id is not None:
                # Ignore replies to other statuses, which happens e.g. when
                # replying to one of our own statuses.
                continue
            self.log.info("Parsing tweet: {0.text}".format(tweet))
            self.parse_mention(tweet)
        
    def parse_mention(self, tweet):
        """Look for the sentence to speak as well as optional flags in the
        tweeter reply.
        """
        # Mention tweets start with @username, remove that.
        username = self.feed.get_screen_name()
        text = re.sub(re.escape("@{0}".format(username)),
                      "",
                      tweet.text,
                      flags=re.IGNORECASE)
        
        # Tweeter gives us times in UTC; convert to the local server time, for
        # scheduling.
        scheduled_at = tweet.created_at.replace(tzinfo=timezone.utc)
        scheduled_at = scheduled_at.astimezone(timezone.Local)
        
        # Remove any extraneous whitespaces
        text = text.strip()
        
        # Parse for arguments
        flags = dict(re.findall("(\w+):(\S+)", text))
        # And remove the arguments from th text
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
                              
        # Send the user some confirmation the message is in the queue
        reply_text = "Queued for {0:%H:%M:%S}. {1}".format(scheduled_at,
                                                           flags_str)
        
        # Add them to the queue
        self.sentence_queue.put((scheduled_at, text, flags))
        self.reply_queue.put((tweet.id, reply_text))
    
