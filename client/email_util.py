# Import smtplib for the actual sending function
import smtplib
import string

# Import the email modules we'll need
from email.mime.text import MIMEText
from printerConfig import *

def send_paper_refill_email(recipients, client_key, base_url):
    text = "when done: %s/settings?client=%s&key=paper_replaced&value=1"%(base_url, client_key)

    #text = "when done: http://partyprint.crudephysics.com/settings?client=foxlover&key=paper_replaced&value=1"
    msg = MIMEText(text)

    me = 'PartyPrint<%s>'%SMTP_USERNAME
    subject = 'reload printer'
    msg['Subject'] = subject
    msg['From'] = me
    msg['To'] = recipients[0]

    '''
    msg = string.join((
            "From: %s" % me,
            "To: %s" % you,
            "Subject: %s" % subject ,
            "",
            text
            ), "\r\n")
    '''


    # Send the message via our own SMTP server, but don't include the
    # envelope header.
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.ehlo()
    server.login(SMTP_USERNAME, SMTP_PASS) # Not very secure, I know, but this email is dedicated to this script
    server.sendmail(me, recipients, msg.as_string())
    server.quit()

