from flask import Flask
from flask import abort
from flask import render_template
from flask import session
from flask import request
from flask import redirect
from flask import url_for
from flask import Response
from instagram import client, subscriptions
from crossdomain import crossdomain

import json
import urllib2, urllib

# ORM imports
from database import db_session
from models import *
from sqlalchemy.exc import *
from sqlalchemy import and_

INSTAGRAM_CLIENT = 'INSTAGRAM_CLIENT_KEY'
INSTAGRAM_SECRET = 'INSTAGRAM_SECRET_TOKEN'
AUTH_REDIRECT = 'auth_complete'
PORT = 8515
HOSTNAME = 'http://my.hostname.com'
VERIFICATION_TOKEN = 'ANY_SECRET_VERIFICATION_TOKEN'
VERBOSE = False

PRINT_READY = 0
PRINT_DONE = 1
PRINT_PENDING = 2
PRINT_ABORTED = 3


# example update
{'changed_aspect': 'media', 'subscription_id': 3541990, 'object': 'tag', 'object_id': 'fox', 'time': 1373146761}
processed_media = set()

def process_tag_update(update):
    if VERBOSE:    
	    print update
    tagname = update['object_id']
    time = update.get('time')
    media = (m for m in 
            api.tag_recent_media(10, min_id=time, tag_name=tagname)[0] if
            m.id not in processed_media)
    
    # Get the clients and subscriptions
    plain_tag = tagname.replace("#", "")
    q = Subscription.query.filter(Subscription.hashtag == plain_tag)
    subs = q.all()
    
    for m in media:
        # Make sure we haven't already grabbed this media
        q = MediaEntry.query.filter(MediaEntry.remote_id == m.id)
        if q.first():
            continue
        
        # Give a media entry for each subscription
        for sub in subs:
            url = m.get_standard_resolution_url()
            entry = MediaEntry(sub.client, sub, url, m.id)
            db_session.add(entry)
        db_session.commit()
            

reactor = subscriptions.SubscriptionsReactor()
reactor.register_callback(subscriptions.SubscriptionType.TAG, 
        process_tag_update)

# Create the app instance
app = Flask(__name__)

# Email server errors
''' TODO: suss this out
ADMINS = ['admin-email@host.com']
if not app.debug:
    import logging
    from logging.handlers import SMTPHandler
    mail_handler = SMTPHandler('mail.hostname.com', 
            'server-error@hostname.com', 
            ADMINS, 'partyprint Failed')
    mail_handler.setLevel(logging.ERROR)
    app.logger.addHandler(mail_handler)
'''

# get the database on it's feet
@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

# Instagram API instance
api = client.InstagramAPI(client_id=INSTAGRAM_CLIENT,
        client_secret=INSTAGRAM_SECRET)

# Create a subscription
def subscribe_to_hashtag(hashtag):
    '''
    Adds a subscription to the given hashtag
    '''
    # Example request
    '''
    curl -F 'client_id=CLIENT-ID' \
         -F 'client_secret=CLIENT-SECRET' \
         -F 'object=tag' \
         -F 'aspect=media' \
         -F 'object_id=nofilter' \
         -F 'callback_url=http://YOUR-CALLBACK/URL' \
         https://api.instagram.com/v1/subscriptions/
     '''

    data = {'client_id':INSTAGRAM_CLIENT,
            'client_secret':INSTAGRAM_SECRET,
            'object':'tag',
            'aspect':'media',
            'object_id':hashtag,
            'verify_token':VERIFICATION_TOKEN,
            'callback_url':HOSTNAME+'/subscription_callback'}
    
    url = "https://api.instagram.com/v1/subscriptions/"
    req = urllib2.Request(url, urllib.urlencode(data))
    
    try:
        response = urllib2.urlopen(req)
        if VERBOSE:
		    print response.read()
    except urllib2.HTTPError, e:
        print "Error", e.code, ":", json.loads(e.read())
        raise

# TODO: convert to requests instead of urllib so that we have a delete method
"""
def delete_all_subscriptions():
    curlcmd = '''curl -X DELETE "https://api.instagram.com/v1/subscriptions?client_secret=%s&object=all&client_id=%s"'''%(INSTAGRAM_SECRET, INSTAGRAM_CLIENT)
    import os
    os.system(curlcmd)
    return
    
    # TODO: figure out how to do a propert DELETE request
    url = "https://api.instagram.com/v1/subscriptions"
    data = {"client_secret":INSTAGRAM_SECRET,
            "client_id":INSTAGRAM_CLIENT,
            "object":"all"}
    
    req = urllib2Ext.RequestWithMethod(url, "DELETE", urllib.urlencode(data))
    response = urllib2.urlopen(req)
    if VERBOSE:
        print response.read()
"""

# database utility functions
def get_client(client_key, default=None):
    client = PartyClient.query.filter(PartyClient.key == client_key).first()
    if client == None:
        return default
    return client

def get_setting(client, setting_key, default=None):
    q = Setting.query.filter(Setting.client == client, 
            Setting.key == setting_key)
    setting = q.first()
    if setting:
        return setting.value
    
    return default


def set_setting(client, setting_key, setting_value):
    q = Setting.query.filter(Setting.client == client,
            Setting.key == setting_key)
    setting = q.first()
    if setting:
        setting.value = setting_value
    else:
        setting = Setting(client, setting_key, setting_value)
        db_session.add(setting)
    db_session.commit()

@app.route("/make_error")
def make_error():
    raise Exception("generic fail")

@app.route("/test")
def test():
    return Response('''
    <div id="loginform">
  <form action="/subscription_callback" method=post>
        <input type='text' size=30 name='email' placeholder="e-mail" /><br />
        <input type='password' size=30 name='password' placeholder="password"/><br />
        <button type='submit' value='login' id='login'>FML</button>
        <button type='submit' name='create' value=1 id='new'>create new</button>
    </form>
</div>
''')

@app.route("/")
def root_page():
    return Response("Nothing to see here :/")

@app.route("/subscription_callback", methods=["GET", "POST"])
@crossdomain(origin='*')
def subscription_callback():
    if VERBOSE:
        print "req method:", request.method
    mode = request.values.get('hub.mode')
    challenge = request.values.get('hub.challenge')
    verify_token = request.values.get('hub.verify_token')
    if False and verify_token != VERIFICATION_TOKEN:
        if VERBOSE:
            print "Bad Verification token:", verify_token
        return Response(json.dumps({"success":False}))

    if challenge:
        if VERBOSE:
            print "challenged with", challenge
        return Response(challenge)
    
    elif request.method == "POST":
        x_hub_signature = request.headers.get('X-Hub-Signature')
        raw_response    = request.data
        try:
            if VERBOSE:
                print "process"
            reactor.process(INSTAGRAM_SECRET, raw_response, x_hub_signature)
        except subscriptions.SubscriptionVerifyError:
            if VERBOSE:
                print 'Instagram signature mismatch'
    return Response(json.dumps({"success":True}))

@app.route("/add_subscription")
def add_subscription():
    client_key = request.args.get("client")
    hashtag = request.args.get("tag")

    if not client_key or not hashtag:
        return Response(json.dumps({"success":False, 
            "msg":"missing args"}))
    
    # store hashtags case insensitive
    hashtag = hashtag.lower()

    # Get the client
    client = get_client(client_key)
    if not client:
        return Response(json.dumps({"success":False, 
            "msg":"client not registered"}))

    # create the instagram subscriptions
    subscribe_to_hashtag(hashtag)

    # do not multi-subscribe
    q = Subscription.query.filter(Subscription.hashtag == hashtag,
            Subscription.client == client)
    if q.count():
        return Response(json.dumps({"success":True}))
    
    sub = Subscription(client, hashtag)
    db_session.add(sub)
    db_session.commit()

    return Response(json.dumps({"success":True}))

@app.route("/add_client")
def add_client():
    client_key = request.args.get("client")
    if not client_key:
        return Response(json.dumps({"success":False, 
            "msg":"you must provide a client"}))
    
    if get_client(client_key):
        return Response(json.dumps({"success":False, 
            "msg":"client exists"}))

    # add the client
    client = PartyClient(client_key)
    db_session.add(client)
    db_session.commit()

    return Response(json.dumps({"success":True}))

@app.route("/media")
def media():
    client_key = request.args.get("client")
    try:
        status = int(request.args["status"])
    except (ValueError, KeyError):
        status = None
    
    client = get_client(client_key)

    if status is None:
        q = MediaEntry.query.filter(MediaEntry.client == client)
    else:
        q = MediaEntry.query.filter(MediaEntry.client == client, 
            MediaEntry.status == status)

    response_list = [{"id":e.id, "url":e.url, "tag":e.subscription.hashtag, 
        "status":e.status} for e in q.all()]
    
    return Response(json.dumps({"success":True, 
        "result":response_list}))

@app.route("/retry")
def retry():
    client_key = request.args.get("client")
    client = get_client(client_key)
    
    if client is None:
        return Response(json.dumps({"success":False, 
            "msg":"you must provide a client"}))
    
    # Get the media that had it's print aborted
    q = MediaEntry.query.filter(MediaEntry.client == client, 
        MediaEntry.status == PRINT_ABORTED)
    for media in q.all():
        media.status = PRINT_READY

    db_session.commit()
    return Response(json.dumps({"success":True}))

@app.route("/mark_media")
def mark_media():
    client_key = request.args.get("client")
    media_id = request.args.get("media_id")
    status = request.args.get("status")
    
    if status is None:
        return Response(json.dumps({"success":False, 
            "msg":"no status given"}))

    try:
        status = int(status)
    except ValueError:
        return Response(json.dumps({"success":False, 
            "msg":"status must be an int"}))

    media_query = MediaEntry.query.filter(PartyClient.key == client_key,
            MediaEntry.id == media_id)

    for media in media_query:
        media.status = status

    db_session.commit()
    return Response(json.dumps({"success":True}))

@app.route('/settings')
def settings():
    client_key = request.args.get("client")
    c = get_client(client_key)
    if c is None:
        return Response(json.dumps({"success":False, 
            "msg":"You must provide a client"}))
    
    setting_key = request.args.get("key")
    setting_value = request.args.get("value")
    
    # Check to see if this is a set request
    if setting_value and not setting_key:
        return Response(json.dumps({"success":False, 
            "msg":"You must provide a key to set value for"}))
    elif setting_value:
        set_setting(c, setting_key, setting_value)
        return Response(json.dumps({"success":True}))
    
    # Handle a single-key request
    if setting_key:
        value = get_setting(c, setting_key)
        return Response(json.dumps({"success":True, "result":value}))

    # roll the client settings into json
    settings = dict(((s.key, s.value) for s in c.settings.values()))
    
    return Response(json.dumps({"success":True, "result":settings}))
    
if __name__ == "__main__":
    app.debug = True
    app.run(host='0.0.0.0', port=PORT)

