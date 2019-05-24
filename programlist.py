#! /usr/bin/env python3

## Version of Feb 12 2016

import sys
sys.path.append('/home/lachaume/Dropbox/python/')

import os
import re
import numpy
import codecs
from MPG.utils import structured_array_from_excel

def get_program_filename(tel, period, path='.', format='xls'):
    basename = 'programmes-{}-P{}.{}'.format(tel, period, format)
    filename = os.path.join(path, basename)
    return filename

class ProgramList(numpy.ndarray):
    def __new__(cls, tel, period, path='.', honour_omit=True):
        path = BasicLog(tel=tel, period=period, path=path).get_path()
        filename = get_program_filename(tel, period, path=path, format='xls')
        arr = structured_array_from_excel(filename, cls=cls) 
        if honour_omit:
            arr = arr[arr['Link'] != 'omit']
        arr.lookup_ = {p: pid for pid in arr['PID'] 
            for p in re.split(',\s*', pid)}
        arr.corr = structured_array_from_excel(filename, cls=cls, sheetnum=1)
        arr.path = path
        arr.tel = tel
        arr.period = period
        for r in range(arr.size):
            ids = arr[r]['Identifiers']
            if len(ids):
                for pid in re.split(',\\s*', ids):
                    arr.lookup_[pid] = arr[r]['PID']
                    arr.period = period
        return arr
    def __getitem__(self, i):
        item = numpy.ndarray.__getitem__(self, i)
        if isinstance(i, str) and i in self.dtype.names:
            item = numpy.array(item.tolist())
        return item
    def lookup(self, pid, target=None, date=None, ins=None):
        # print('lookup', pid, ins)
        if target is not None or date is not None:
            # print(self.corr)
            for line in self.corr:
                if line['PID'] in pid:
                    t = line['Target']
                    d1, d2 = line['Start'], line['End']
                    # print((line['PID'], t, d1, date, d2))
                    if t != '' and not re.search(t, target):
                        continue
                    if d1 != '' and date < d1:
                        continue
                    if d2 != '' and date > d2:
                        continue
                    pid = line['Nominal PID']
        if pid in self['PID']:
            return self[self['PID'] == pid][0]
        try:
            return self[self.lookup_[pid] == self['PID']][0]
        except:
            prog = self[-1].copy()
            prog['TAC'] = 'N/A'
            prog['PID'] = pid
            prog['Title'] = 'Unidentified programme'
            prog['Surname'] = 'Unknown'
            prog['Name'] = ''
            prog['Instrument'] = ins
            prog['Identifiers'] = '???'
            prog['Link'] = 'no'
            return prog
    def save_as_html(self):
        ESOURL = 'http://archive.eso.org/wdb/wdb/eso/sched_rep_arc/query'
        tel, period, path = self.tel, self.period, self.path
        filename = get_program_filename(tel, period, path=path, format='htm')
        fh = codecs.open(filename, 'wb', 'utf-8')
        fh.write('  <tbody>\n')
        last_tac = None
        for row in self:
            tac, pid, link = row['TAC'], row['PID'], row['Link']
            title, pi = row['Title'], row['Name'] + ' ' + row['Surname']
            if pid != 'TBD':
                # Link to proposal 
                if link != 'no':
                    if link[0:7] == 'http://':
                        url = link
                    else:
                        url = 'proposals/'
                        if link == 'yes':
                            if period >= 100:
                                url += pid[7:11] + '.pdf'
                            else:
                                url += pid[6:10] + '.pdf'
                        else:
                            url += link + '.pdf'
                    title = '<a href="{}">{}</a>'.format(url, title)
                # Fix PID and link to archive
                # print(tac, pid, link, title, pi)
                if pid[-1] != ')':
                    print('fix pid:', pid)
                    pid += '(A)'
                link = '{}?progid={}'.format(ESOURL, pid)
                pid = '<a href="{}">{}</a>'.format(link, pid)
            cols = [tac, pid, pi, row['Instrument'], title, row['Hours'], 
                    row['Moon'], row['Trans.'], row['Seeing'], row['Airmass']]
            # Not breakable
            for i in [1, 2]:
                cols[i] = '<span class="atomic">{}</span>'.format(cols[i])
            if last_tac is not None and last_tac != tac:
                fh.write('  </tbody><tbody>\n')
            last_tac = tac
            fh.write('    <tr>\n')
            for col in cols:
                fh.write(u'      <td>{}</td>\n'.format(col))
            fh.write('    </tr>\n')
        fh.write('  </tbody>')
    def publish_to(self, rdir):
        tel, period, path = self.tel, self.period, self.path
        rdir = '{}/P{}'.format(rdir, period)
        filename = get_program_filename(tel, period, path=path, format='htm')
        os.system('scp -r {} {}/proposals {}'.format(filename, path, rdir))



from MPG.esolog import BasicLog
