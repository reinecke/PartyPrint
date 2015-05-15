#from flask.ext.sqlalchemy import SQLAlchemy
import datetime

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, backref
from database import Base

#db = SQLAlchemy()

ENTRY_STATUS_NEW = 0
ENTRY_STATUS_PROCESSED = 1

class PartyClient(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True)
    subscriptions = relationship("Subscription",
            primaryjoin="Subscription.client_id==PartyClient.id")
    setting_objs = relationship("Setting",
            primaryjoin="Setting.client_id==PartyClient.id")
    
    @property
    def settings(self):
        '''
        Returns a dictionary with setting keys as keys, and setting objects
        as values.
        '''
        return dict(((s.key, s) for s in self.setting_objs))

    def __init__(self, key):
        '''
        Key is a unique key that this client identifies itself as
        '''
        self.key = key

    def __repr__(self):
        return "<PartyClient: %r>" % self.key

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    client = relationship(PartyClient, primaryjoin=client_id == PartyClient.id)
    hashtag = Column(String(64))

    def __init__(self, client, hashtag):
        self.client = client
        self.hashtag = hashtag

    def __repr__(self):
        return "<Subscription %d for:%s to:%s>"%(self.id, self.client.key,
                self.hashtag)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(64), primary_key=True)
    value = Column(String(64))
    client_id = Column(Integer, ForeignKey("clients.id"), primary_key=True)
    client = relationship(PartyClient, primaryjoin=client_id == PartyClient.id)
    #__table_args__ = (ForeignKeyConstraint([client_id, key],
    #    [Setting.client_id, Setting.))
    
    def __init__(self, client, key, value):
        self.client = client
        self.key = key
        self.value = value

    def __repr__(self):
        return "<Setting for %s %s:%s>"%(self.client.key, self.key, self.value)


class MediaEntry(Base):
    __tablename__ = "media_entries"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    client = relationship(PartyClient,
            primaryjoin=client_id == PartyClient.id)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"))
    subscription = relationship(Subscription, 
            primaryjoin=subscription_id == Subscription.id)
    status = Column(Integer)
    url = Column(String(256))
    remote_id = Column(String(64))

    def __init__(self, client, subscription, url, remote_id):
        self.client = client
        self.subscription = subscription
        self.url = url
        self.remote_id = remote_id

        self.status = ENTRY_STATUS_NEW

    def __repr__(self):
        return "<Entry:%d for client:%s status:%d URL:%s>"%(self.id, 
                self.client.key, self.status, self.url)

