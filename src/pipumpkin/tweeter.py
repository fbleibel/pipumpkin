"""
Interface to the tweeter API

A single tweeter account is used to receive the sentences to speak as well as
post updates on their registration on the queue.

This account must have an application registered with Read & Write rights. The
corresponding tokens are read from a file (by default /etc/pipumpkin-auth-tokens
), which should be a json dictionary with the keys "consumer-key",
"consumer-secret", "access-token", "access-secret". You can get the first two by
registering your application with twitter (e.g. "pipumpkin"), the second two by
authorising your application with the corresponding account (e.g "pipumpkin").
"""
import json
import logging
import traceback
import tweepy

class FeedError(Exception):
    """Base class for errors from this module
    """

class TweeterFeed(object):
    """Expose some helper methods to use the tweeter API
    """
    def __init__(self, tokens_path=None):
        """
        """
        self.log = logging.getLogger("pipumpkin")
        self.tokens_path = tokens_path or "/etc/pipumpkin-auth-tokens"
        with open(self.tokens_path, "r") as file:
            tokens = json.load(file)
        auth = tweepy.OAuthHandler(tokens["consumer-key"],
                                   tokens["consumer-secret"])
        auth.set_access_token(tokens["access-token"], tokens["access-secret"])
        self.api = tweepy.API(auth)
        self.cached_screen_name = None

    def tweet_alive(self, status=""):
        """Post a generic status to tell the world that that deamon is alive
        and running. An optional status can be passed in.
        
        Note: swallow exceptions as 
        
        Returns:
            True if tweeting the alive status has suceeded, False otherwise.
        """
        tweet = ("I'm alive! (%s)" % status)[:140]
        try:
            self.api.update_status(tweet)
        except tweepy.TweepError:
            self.log.error(traceback.format_exc())
            return False
        return True
    
    def get_screen_name(self):
        """Return the screen name of the user we're connected to. The first
        invocation may be slow; subsequent calls return the cached screen name.
        """
        if not self.cached_screen_name:
            self.cached_screen_name = self.api.me().screen_name
        return self.cached_screen_name
    
    def get_latest_mention_id(self):
        """Returns the id of the latest tweet that mentions the current user,
        or None. May raise FeedError if there was an error retrieving this ID,
        possibly because of rate limiting.
        """
        cursor = tweepy.Cursor(self.api.mentions_timeline)
        try:
            tweet = next(cursor.items())
            return tweet.id
        except tweepy.TweepError as e:
            self.log.error(traceback.format_exc())
            raise FeedError(str(e))
        except StopIteration:
            return None
        
    def get_mentions_after(self, since_id):
        """Returns all tweets from the "mentions" queue created after the tweet
        referred to via since_id. If since_id is None, returns all
        mentioned tweets. May raise FeedError if there was an error retrieving
        the mentions, e.g. if the twitter rate limiting is hit.
        """
        if since_id:
            cursor = tweepy.Cursor(self.api.mentions_timeline,
                                   trim_user=True,
                                   since_id=since_id)
        else:
            cursor = tweepy.Cursor(self.api.mentions_timeline, trim_user=True)
        try:
            result = list(cursor.items())
        except tweepy.TweepError as e:
            self.log.error(traceback.format_exc())
            raise FeedError(str(e))
        return result
        
    def post_reply(self, reply_to_id, reply_text):
        """Post a reply to the tweet referred to by 'reply_to_id'. Returns True
        if the status update was successful, False otherwise.
        """
        text = "@{0} {1}".format(self.get_screen_name(),
                                 reply_text)[:140]
        try:
            self.api.update_status(text, in_reply_to_status_id=reply_to_id)
        except tweepy.TweepError:
            self.log.error(traceback.format_exc())
            return False
        return True
        
