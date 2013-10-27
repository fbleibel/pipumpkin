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
import traceback
import tweepy

class TweeterFeed(object):
    """Expose some helper methods to use the tweeter API
    """
    def __init__(self, tokens_path=None):
        """
        """
        self.tokens_path = tokens_path or "/etc/pipumpkin-auth-tokens"
        with open(self.tokens_path, "r") as file:
            tokens = json.load(file)
        auth = tweepy.OAuthHandler(tokens["consumer-key"],
                                   tokens["consumer-secret"])
        auth.set_access_token(tokens["access-token"], tokens["access-secret"])
        self.api = tweepy.API(auth)

    def tweet_alive(self, status=""):
        """Post a generic status to tell the world that that deamon is alive
        and running. An optional status can be passed in.
        
        Note: swallow exceptions as 
        
        Returns:
            True if tweeting the alive status has suceeded, False otherwise.
        """
        tweet = ("I am alive! %s" % status)[:140]
        try:
            self.api.update_status(tweet)
        except tweepy.TweepError:
            traceback.print_exc()
            return False
        return True
