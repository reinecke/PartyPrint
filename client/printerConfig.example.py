#!/usr/bin/env python
import os

### General/server settings ###
CLIENT_KEY = 'nameRegisteredWithServer'
SERVER_URL = 'http://partyprint.mydomain.com'
DATA_DIR = os.path.join(os.path.expanduser('~'), '.partyPrinter', CLIENT_KEY)
MAX_RETRY = 3

### Polaroid GL10 Settings ###
PRINTER_CAPACITY = 10 # Number of pages the printer holds
PRINTER_ID = "86:75:30:9F:DE:F7" # Bluetooth ID of printer
PRINT_SERVICE_CHANNEL = "1" # BT devices have diff services on different channel
PRINT_DRYRUN = False # Set to True to skip the actual printing

### E-MAIL Notification Settings ###
# the list of e-mail addresses below will get sent e-mails when the printer
# paper count hits zero. I like to use the e-mail to text brige my wireless
# company provides
PAPER_REFILL_RECIPIENTS = ['5558675309@expensivewireless.net']
SMTP_USERNAME = 'myUsername@gmail.com'
SMTP_PASS = 'myPassword'
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

