import imaplib
import getpass
import email

from MPG.utils import get_period_limits
from datetime import timedelta

def parse_mail(mail, id):
    resp, data = mail.fetch(id, '(RFC822)'))
    if resp != 'OK':
        return None
    msg = data[0][1]

def get_mail(mail, period):
    day = timedelta(days=1) 
    start, end = get_period_limits(period)
    start = (start - day).strftime('%d-%b-%Y')
    end = (end + day).strftime('%d-%b-%Y')
    searchstr = 'SENTSINCE {} SENTAFTER {}'.format(start, end)
    resp, idlist = mail.search(None, searchstr)
    ids = idlist[0].split()
    for id in ids:
        action, reason = parse_mail(mail, id)


mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login('regis.lachaume@gmail.com', getpass.getpass())
mail.select('lsops')
resp, idlist = mail.search(None, '(SINCE )')
ids = idlist[0].split()

