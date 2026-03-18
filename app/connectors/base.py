"""Connectors for discovering marketers from external sources."""
import os
import requests


class RedditConnector:
    def __init__(self):
        self.client_id = os.environ.get('REDDIT_CLIENT_ID', '')
        self.client_secret = os.environ.get('REDDIT_CLIENT_SECRET', '')
        self.user_agent = os.environ.get('REDDIT_USER_AGENT', 'soundmatch/1.0')

    def discover(self, subreddits=None):
        return []


class WebDirectoryConnector:
    def __init__(self):
        self.directories = []

    def discover(self):
        return []
