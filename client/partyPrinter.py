#!/usr/bin/env python
import os, sys, subprocess, shutil, tempfile, commands, time, argparse

import urllib
import urllib2
import json
from urlparse import urlparse
import posixpath
import time

from prepImage import add_overlay
from email_util import send_paper_refill_email

from printerConfig import *

PRINT_READY = 0
PRINT_DONE = 1
PRINT_PENDING = 2
PRINT_ABORTED = 3
PRINT_SKIPPED = 4

STATE_IDLE = 0
STATE_PRINTING = 1
STATE_FETCHING = 2
STATE_WAITING_FOR_PAPER = 3
STATE_SENDING_PRINT = 4

SLEEP_DELAY = {STATE_IDLE:10, STATE_PRINTING:5, STATE_FETCHING:2, 
        STATE_WAITING_FOR_PAPER:10, STATE_SENDING_PRINT:4}

class APIError(Exception): pass

def get_ip(iface='wlan0'):
    '''
    Super ghetto way to get the ip for the device
    '''
    cmd = 'ifconfig %s | grep "inet addr"' % iface
    return commands.getoutput(cmd).split("inet addr:")[1].split(' ')[0]

def _api_request(path, data):
    url = SERVER_URL+'/'+path
    request_data = {'client':CLIENT_KEY}
    request_data.update(data)
    
    retry = True
    while(retry):
        try:
            req = urllib2.Request(url+"?"+urllib.urlencode(request_data))
            response = urllib2.urlopen(req)
        except Exception, e:
            print "Error executing request: %s with %s" %(path, request_data)
            print e
            print "Will Retry"
            time.sleep(5)
            continue
        
        retry = False

        result = json.loads(response.read())
        if not result.get("success"):
            e = APIError(result.get("msg"))
            raise e
    
    return result.get('result')

def get_prints(status=PRINT_READY):
    return _api_request('media', {'status':status})
    
def mark_print(print_id, status=PRINT_DONE):
    _api_request('mark_media', {'status':status, 'media_id':print_id})

def set_setting(key, value):
    _api_request('settings', {'key':key, 'value':value})

def get_setting(key):
    return _api_request('settings', {'key':key})

class PartyPrinter(object):
    def __init__(self):
        self.current_state = STATE_IDLE
        self.current_media_id = None
        self.current_media_url = None
        self.retry_count = 0
        
        self.current_remaining_pages = PRINTER_CAPACITY
        
        self._download_proc = None
        self._print_proc = None

        self._pending_download_path = None

        self._pending_print_path = None
        
        self.has_sent_paper_note = False

        # ensure a data dir exists
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

        for dirpath in (self.finished_print_dir, self.finished_download_dir):
            if not os.path.exists(dirpath):
                os.makedirs(dirpath)
    
    @property
    def finished_download_dir(self):
        return os.path.join(DATA_DIR, "downloaded")

    @property
    def finished_print_dir(self):
        return os.path.join(DATA_DIR, "printed")

    def media_path_for_id(self, media_id, ext):
        return os.path.join(self.finished_download_dir, 
                "media.%d%s"%(media_id, ext))
        
    def log_error(self, error):
        print >> sys.stderr, error

    def log(self, msg):
        print >> sys.stdout, msg
    
    def reset_current_media(self):
        self.retry_count = 0
        self.current_media_url = None
        self.current_media_id = None
        self._pending_download_path = None
        self._pending_print_path = None
        self._print_proc = None
        self.has_sent_paper_note = False

    def check_for_media(self):
        self.log("checking for media...")
        prints = get_prints()
        self.log("%d ready prints found"%len(prints))
        if not prints:
            return
        
        # Select something to download and print
        selected_print = prints[0]
        self.current_media_id = selected_print['id']
        self.current_media_url = selected_print['url']
        
        # Get the ball rolling!
        self.launch_download()

    def check_download(self):
        '''
        Check the download and see if we should move on to the next task
        '''
        result = self._download_proc.poll()
        
        # Still running, wait for the next nudge
        if result is None:
            return
        
        # Download done, clear the proc
        self._download_proc = None

        # If the curl op failed, try re-launching
        if result != 0:
            self.retry_count += 1
            self.log("retry: "+self.current_media_url)

            # Abort if retry count maxed out
            if self.retry_count > MAX_RETRY:
                mark_print(self.current_media_id, PRINT_ABORTED)
                self.log_error("Aborted printing %s, max retry reached"%
                        self.current_media_id)
                self.reset_current_media()
                self.current_state = STATE_IDLE
                return
            
            # Retry the download
            self.launch_download()

        # Move the media to the right location
        self.log("Download done: "+self.current_media_url)
        ext = os.path.splitext(self._pending_download_path)[1]
        media_path = self.media_path_for_id(self.current_media_id, ext)
        if os.path.exists(media_path):
            os.remove(media_path)
        shutil.move(self._pending_download_path, media_path)
        
        # Move on to printing
        self.launch_send_print()

    def check_print(self):
        # Copy the finished print to the archive
        ext = os.path.splitext(self._pending_print_path)[1]
        media_path = self.media_path_for_id(self.current_media_id, ext)
        dest_name = os.path.splitext(os.path.basename(media_path))[0]+".jpg"
        dest_path = os.path.join(self.finished_print_dir, dest_name)
        #if os.path.exists(media_path):
        #    os.remove(media_path)
        shutil.copy(self._pending_print_path, dest_path)
        
        # go back to idle
        mark_print(self.current_media_id, PRINT_DONE)
        self.log("print done: %s"%media_path)
        self.reset_current_media()
        self.current_remaining_pages -= 1

        # Check the pages
        if self.current_remaining_pages == 0:
            self.log("Out of paper...")
            self.current_state = STATE_WAITING_FOR_PAPER
            set_setting("paper_replaced", 0)
        else:    
            self.current_state = STATE_IDLE

    def check_for_paper(self):
        if not self.has_sent_paper_note:
            try:
                send_paper_refill_email(PAPER_REFILL_RECIPIENTS, 
                    CLIENT_KEY, SERVER_URL)
                self.has_sent_paper_note = True
            except:
                pass
        try:
            paper_replaced = int(get_setting("paper_replaced"))
        except (ValueError, TypeError):
            paper_replaced = 0

        if not paper_replaced:
            return
        self.current_remaining_pages = PRINTER_CAPACITY
        set_setting("paper_replaced", 0)
        self.current_state = STATE_IDLE

    def check_sending_print(self):
        result = self._print_proc.poll()
        if result is None:
            return
        
        # If the send op failed, skip
        if result != 0:
            mark_print(self.current_media_id, PRINT_ABORTED)
            self.log_error("Aborted printing %s, error sending to printer"%
                    self.current_media_id)
            self.reset_current_media()
            self.current_state = STATE_IDLE
            return
        
        # looks good, start the print
        self.launch_print()

    # Table that given a state, tells which method to call to advance to
    # next state
    dispatch_table = {STATE_IDLE:check_for_media, 
            STATE_FETCHING:check_download,
            STATE_PRINTING:check_print, 
            STATE_WAITING_FOR_PAPER:check_for_paper,
            STATE_SENDING_PRINT:check_sending_print}

    def nudge_state(self):
        '''
        Nudges the state on the state machine
        '''
        
        fn_to_run = self.dispatch_table[self.current_state]
        fn_to_run(self)

    def launch_download(self):
        '''
        Starts a download of media
        '''
        self.log("fetching: "+self.current_media_url)
        # set the state
        self.current_state = STATE_FETCHING
        
        # find a place to put the file
        parsed_url = urlparse(self.current_media_url)
        ext = posixpath.splitext(parsed_url.path)[1]
        fh,self._pending_download_path = tempfile.mkstemp(ext, 
            "partyPrinter.")
        os.close(fh)

        # Start the download
        cmd = ["curl", '-o', self._pending_download_path, 
                self.current_media_url]
        self._download_proc = subprocess.Popen(cmd)
        
    def launch_send_print(self):
        '''
        Starts a print of media
        '''
        self.current_state = STATE_SENDING_PRINT
        mark_print(self.current_media_id, PRINT_PENDING)

        # Grab the finished download
        ext = os.path.splitext(self._pending_download_path)[1]
        media_path = self.media_path_for_id(self.current_media_id, ext)
        self.log("Starting print: %s"%media_path)
        
        # add an overlay to a tempdir
        fh,fpath = tempfile.mkstemp(".jpg", 
            "partyPrinter.print.")
        os.close(fh)
        
        try:
            add_overlay(media_path, fpath)
        except IOError:
            mark_print(self.current_media_id, PRINT_ABORTED)
            self.log_error("Aborted printing: %s, could not read image"%
                    media_path)
            self.reset_current_media()
            self.current_state = STATE_IDLE
            return

        self._pending_print_path = fpath
        
        dest_name = os.path.splitext(os.path.basename(media_path))[0]+".jpg"
        cmd = ['ussp-push', PRINTER_ID + "@" + PRINT_SERVICE_CHANNEL, 
                fpath, dest_name]
        
        if PRINT_DRYRUN:
            self.log("Would print with command:"+' '.join(cmd))
            class dummy(object):
                def poll(self): return 0
            self._print_proc = dummy()
        else:
            self.log("Sending print with command:"+' '.join(cmd))
            self._print_proc = subprocess.Popen(cmd)

    def launch_print(self):
        self.current_state = STATE_PRINTING
        # Stupid phase to give the printer time to print
        self.log("Waiting for print...")
        time.sleep(41)

        
def parse_args():
    parser = argparse.ArgumentParser(
    description='auto-print new photos for this printer')
    parser.add_argument('--pages', type=int, default=PRINTER_CAPACITY,
        help='number of pages currently in the printer')

    args = parser.parse_args()

    return args

def main():
    '''
    main run loop
    '''
    args = parse_args()

    printer = PartyPrinter()
    
    # Set the page count to the user-defined page count
    printer.current_remaining_pages = args.pages

    # Tell the server our ip
    set_setting('ip', get_ip())
    
    previous_state = None
    while(True):
        try:
            printer.nudge_state()
        except:
            print >> sys.stderr, "trouble on id:%s"%printer.current_media_id
            import traceback;traceback.print_exc()
            print >> sys.stderr, "restarting..."
            
            try:
                # Skip the offending print
                mark_print(printer.current_media_id, PRINT_ABORTED)
            except:
                # if there are network issues, we don't want that to kill our
                # recovery
                pass

            # Just in case, lets err on the side of a page having been consumed
            pages_left = printer.current_remaining_pages - 1
            
            # Build a clean printer state machine and move on
            printer = PartyPrinter()
            printer.current_remaining_pages = pages_left
            

        print "printer state:", printer.current_state
        print "sheets remaining:", printer.current_remaining_pages
        
        # Determine the sleep time
        delay = 0
        if printer.current_state == previous_state:
            delay = SLEEP_DELAY.get(printer.current_state, 5)
        previous_state = printer.current_state
        
        time.sleep(delay)

if __name__ == "__main__":
    main()
