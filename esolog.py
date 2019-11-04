#! /usr/bin/env python3

## Version of Feb 12 2016

import sys
sys.path.append('/home/lachaume/Dropbox/python/')

from MPG.utils import structured_array_from_excel
from MPG.esoarchive import NightRequest

import numpy
import re
import urllib.request, urllib.parse
import os, re, sys, time, warnings, iso8601, datetime, ephem
from numpy import sqrt, hstack, arange, array, unique, pi
from astropy.io.votable import parse_single_table
from astropy.io import fits as pyfits
from copy import copy, deepcopy
import asciitable
import io
import pylab
from MPG.gtable import Table, Column, TableGroups
import itertools

warnings.filterwarnings('ignore') 

def attr_completion(row):
    t_alloc, t_exec = float(row[5]), float(row[7])
    attr = {'class': 'scheduled'}
    if t_exec > 0:
        attr['class'] = 'ongoing'
    if t_alloc > 0:
        if t_exec > 0.9 * t_alloc:
            attr['class'] = 'completed'
    return attr

def attr_na(name, el):
    attr = {}
    if el == '-100%':
        attr['class'] = 'invisible'
    return attr 

def write_program_report(progs, progfile, info=''):
    progs.write(progfile, repeat_header=False,
        show_units=True,
        format='ascii.html_with_groups',
        exclude_names=['Name', 'Moon', 'Trans.', 'Seeing',
            'Airmass', 'Title', 'Link', 'Identifiers'],
        htmldict={'table_attr': {'class': 'horizontal'},
            'tr_attr_fun': attr_completion,
            'td_attr_fun': attr_na,
            'caption': 'Program completion ' + info})

def write_telescope_use_report(use, usefile, info=''):
    use.write(usefile, repeat_header=False, show_units=True,
                    format='ascii.html_with_groups',
                    htmldict={'table_attr': {'class': 'horizontal'},
                     'caption': 'Report on facility use ' + info})


# Date manipulation #######################################################

def date_to_night(date, lon):
    # Converts to mean solar time, 12 hours before
    # It always fall on the day before the night starts
    seconds = (lon / 360. - 0.5) * 86400
    night = add_overhead(date, seconds=seconds)
    return numpy.array([n[0:10] for n in night])

def format_night_str(year=None, month=None, day=None):
  # ESO archive unexpectedly expects night to have dd mm yyyy format.
  # We use ISO date for the file
  if year is None:
    t = time.gmtime()
    night = '{0:02} {1:02} {2:04}'.format(*t)
    isodate = '{2:04}-{1:02}-{0:02}'.format(*t)
  elif type(year) is str:
    isodate = year
    m = re.match('([0-9]{4})-([0-9]{2})-([0-9]{2})', isodate)
    night = ' '.join(m.groups()[::-1])
  else:
    night = '{0:02} {1:02} {2:04}'.format(day, month, year)
    isodate = '{2:04}-{1:02}-{0:02}'.format(day, month, year)
  return night, isodate

def parse_date(s):
    if numpy.ndim(s):
        return numpy.array([parse_date(x) for x in s])
    return iso8601.parse_date(str(s))

def isoformat(s):
    if numpy.ndim(s):
        return numpy.array([isoformat(x) for x in s])
    return s.isoformat()[0:19]

def time_delta(a, b):
    dt = parse_date(b) - parse_date(a)
    if numpy.ndim(dt):
        return numpy.array([x.total_seconds() / 3600. for x in dt])
    return dt.total_seconds() / 3600.

def daterange(a, b):
     numpy.hstack([numpy.arange(a, b), b])

def lastnight():
    return datetime.date.today() - datetime.timedelta(hours=36)

# Utils #####################################################################

def listdir(directory, ext=[]):
  regex = '(' + '|'.join(numpy.atleast_1d(ext)) + ')$'
  filenames = [os.path.join(directory, f) 
                 for f in os.listdir(directory) if re.search(regex, f)]
  return sorted(filenames)

def get_dtype(dflt, fmt=''):
    arr = numpy.array(dflt)
    if arr.dtype.char in 'SU' and fmt != '':
        return numpy.array(fmt.format(dflt)).dtype
    return arr.dtype

def mkdir(d):
  try:
    os.makedirs(d)
  except OSError as e:
    if e.errno != 17:
      raise e

def min(a, b):
    a1, b1 = numpy.broadcast_arrays(a, b)
    if numpy.ndim(a1) == 0:
        return a if a < b else b
    c1 = numpy.copy(a1)
    index = b1 < a1
    c1[index] = b1[index]
    return c1

def max(a, b):
    a1, b1 = numpy.broadcast_arrays(a, b)
    if numpy.ndim(a1) == 0:
        return a if a > b else b
    c1 = numpy.copy(a1)
    index = b1 > a1
    c1[index] = b1[index]
    return c1

def add_overhead(strdate, seconds=0):
    if numpy.ndim(strdate) == 0 and numpy.ndim(seconds) == 0:
        newdate = parse_date(strdate) + datetime.timedelta(seconds=seconds)
        return isoformat(newdate)
    date, sec = numpy.broadcast_arrays(strdate, seconds)
    return numpy.array([add_overhead(d, s) for d, s in zip(date, sec)]) 

def report(verbose, string, *arg, **kwarg):
    if verbose > 0:
        print(string.format(*arg, **kwarg))


# Basic Log #################################################################

class BasicLog(Table):
    instruments = {
        '2.2m': ['FEROS', 'WFI', 'GROND'],
        '3.6m': ['HARPS'],
        'NTT': ['EFOSC', 'SOFI']
    }
    keywords = Table.read('/home/lachaume/Dropbox/bin/esolog.dat',
        format='ascii.fixed_width_two_line')
    def __init__(self, *arg, names=None, tel=None, 
                        period=None, night=None, path='.', 
                        mirror='http://archive.eso.org', meta=None, **kwarg):
        print('Start of init')
        columns = self.keywords.columns
        names = columns['name'].tolist()
        types = columns['type'].tolist()
        self.primary_key = None
        self._copy_indices = True
        self._init_indices = True
        if 'copy' not in kwarg or kwarg['copy'] is True:
            kwarg['dtype'] = types
            kwarg['names'] = names
        super().__init__(*arg, **kwarg)
        # if _meta is given, don't do initialisations.
        if meta is not None:
            print('Skip computations and use meta')
            self.meta = meta.copy()
        elif tel is None:
            print('Skip computation and do not initialise')
        else:
            print('Compute ephemeris')
            self.meta['mirror'] = mirror
            self.meta['path'] = path
            self.meta['telescope'] = tel
            if period is not None:
                self.meta['period'] = period
            if night is not None:
                self.meta['night'] = night
                if period is None:
                    self.meta['period'] = self.night_to_period(night)
            if night is not None or period is not None:
                self.set_ephemeris()
                self.set_comments()
        print('End of __init__')
    @staticmethod
    def night_to_period(night):
        # Determine ESO period (every 6 months starting Oct. 1st and Apr. 1st
        if numpy.ndim(night) == 1:
            return [night_to_period(n) for n in night]
        night = str(night)
        year, month, day = int(night[0:4]), int(night[5:7]), int(night[8:10])
        period = 94 + 2 * (year - 2015) + (month > 3) + (month > 9)
        return period
    @classmethod
    def get_defaults(cls):
        defaults = cls.keywords.default
        types = cls.keywords.type
        widths = cls.keywords.width
        #defaults = [eval(t)(d).ljust(w) if t == 'str' else eval(t)(d)
        #        for d, t, w in zip(defaults, types, widths)]
        defaults = [array(d, dtype=t) 
                for d, t, w in zip(defaults, types, widths)]
        return tuple(defaults)
    def get_header(self, dataid, verbose=1, clobber=False):
        dataid = dataid.decode()
        path = self.get_path()
        mirror = self.mirror
        if verbose <= 0:
            warnings.filterwarnings('ignore')
        filename = os.path.join(path, dataid) + '.fits.hdr'
        report(verbose, 'Get header for {}', dataid)
        if not clobber:
            try:
                header = pyfits.Header.fromtextfile(filename)
            except:
                clobber = True
        if clobber:
            url = mirror + '/hdr?DpId=' + dataid
            report(verbose, 'Download header ' + filename)
            ok = False
            while not ok:
                try:
                     with urllib.request.urlopen(url) as response:
                          page = response.read().decode('utf-8')
                     ok = True
                except urllib.request.URLError as error:
                     if error.errno != 110:
                         raise error
            h = re.search('<pre>(.*)</pre>', page, flags=re.S).groups()[0]
            h = ''.join(l[0:80] + ' ' * (80 - len(l[0:80])) for l in h.splitlines())
            h += ' ' * (2880 - (len(h) % 2880))
            header = pyfits.Header.fromstring(h)
            mkdir(path)
            try:
                header.toTxtFile(filename, clobber=True)
            except:
                header.totextfile(filename, clobber=True)
        return header
    def get_night_list(self, verbose=1, clobber=False):
        mirror = self.mirror
        if verbose <= 0:
            warnings.filterwarnings('ignore')
        tel = self.telescope
        instruments = self.instruments[tel]
        # Date
        night, isodate = format_night_str(self.get_night())
        tel = self.telescope
        filepath = self.get_path()
        filename = self.get_path(fileext='xml')
        # filename = os.path.join(path, isodate + '.xml')
        report(verbose, 'Get night log {}', filename)
        #
        # Try to read the file
        #
        if not clobber:
            try:
                table = parse_single_table(filename, pedantic=False)
            except:
                clobber = True
        # 
        # Get the ESO archive
        #
        if clobber:
            url = mirror + '/wdb/wdb/eso/eso_archive_main/query'
            # instrument query 
            request = NightRequest(night, inslist=instruments,  
                    output='votable/display', tab_exptime='on',
                    tab_instrument='on', tab_dp_id='on')
            #inslist = ["(ins_id like '{0}%')".format(i) for i in instruments]
            #insquery = '(' + ' or '.join(inslist)  + ')'
            # form & query
            #form = urllib.parse.urlencode({
            #    'night': night, 'add': insquery,
            #    'tab_dp_id': 'on', 'wdbo': 'votable/display',
            #    'max_rows_returned': 999999,
            #    'tab_exptime': 'on', 'tab_instrument': 'on',
            #})
            #form = form.encode('utf-8')
            #report(verbose, 'Downloading night log for {}', isodate)
            with request.urlopen() as response:
                page = response.read()
            # save file and load it
            mkdir(filepath)
            report(verbose, 'Writing night log {}', filename)
            open(filename, 'wb').write(page)
            table = parse_single_table(filename, pedantic=False)
        array = table.array
        #keep = (array['ins_id'] != b'GROND') + (array['exptime'] != 10)
        #array = array[keep]
        # 2018-02-20
        # return array['dp_id']
        return array['dp_id'].data
    @staticmethod
    def load_keyword(row, header):
        dtype = numpy.dtype(row['type'])
        value = dtype.type(row['default'])
        for fits_key in row['fits_keys'].split(','):
            if fits_key == '--':
                break
            if fits_key in header:
                value = header[fits_key]
                break
        if isinstance(value, (bytes, str)):
            width = row['width']
            value = value.ljust(row['width']) 
        return value
    @classmethod
    def load_keywords(cls, header):
        if isinstance(header, str):
            with pyfits.open(header) as h:
                return cls.load_keywords(h)
        values = [cls.load_keyword(row, header) for row in cls.keywords]
        return values
    def date_interval(self, name, time_only=False, time_value=False):
        date = self.meta[name]
        t = sum(time_delta(d1, d2) for d1, d2 in date)
        if time_value:
            return t
        if time_only:
            return '{:.2f} h'.format(t)
        inter = ['{}-{}'.format(d1[11:19], d2[11:19]) for d1, d2 in date]
        inter = ','.join(inter)
        return '{:.2f} h ({})'.format(t, inter)
    def get_comments(self, concat=False):
        value = self.meta['comments'] 
        if concat:
            value = os.linesep.join(value)
        return value
    def set_comments(self, value, concat=False):
        if concat:
            value = value.split(os.linesep)
        if value is not None:
            self.meta['comments'] = value
    def set_ephemeris(self):
        self.ephemeris = False
    def get_path(self, level=None, fileext=None):
        path = self.meta['path']
        if level not in ['base']:
            filename = self.meta['telescope']
            path = os.path.join(path, filename)
        if 'period' in self.meta and level not in ['tel', 'base']:
            filename = 'P{}'.format(self.meta['period'])
            path = os.path.join(path, filename)
        if 'night' in self.meta and level not in ['tel', 'base', 'period']:
            filename = str(self.meta['night'])
            path = os.path.join(path, filename)
        if fileext is not None:
            if '.' not in fileext:
                fileext = '.' + fileext
            path = os.path.join(path, filename + fileext)
        return path
    @classmethod
    def read(cls, tel, period=None, night=None, filename=None, clobber=None, 
            clobberHeaderList=False, clobberLastNights=False, compact=True,
            format= 'ascii.fixed_width_two_line', fileext='.dat', path='.',
            **kwarg):
        print('def read', cls)
        iokwarg = {a: b for a,b in kwarg.items() if a[:7] != 'clobber'}
        clobberarg = {a: b for a,b in kwarg.items() if a[:7] == 'clobber'}
        emptylog = cls(tel=tel, period=period, night=night, path=path)
        print('empty log done')
        if night is not None and clobberLastNights:
            dt = datetime.date.today() - parse_date(night).date()
            if dt.total_seconds() < 3 * 86400:
                clobber = True
                clobberHeaderList = True
        if filename is None:
            filename = emptylog.get_path(fileext=fileext)
        if not clobber:
            print('try to read log', night, period)
            try:
                log = super().read(filename, format=format, 
                        fill_values=None, **iokwarg)
                print('sucess reading', type(log).__name__, night, period)
                for col in log.colnames:
                    if ' ' in col:
                        log.columns[col].name = re.sub(' ', '_', col)
                log = cls(log, meta=emptylog.meta)
            except:
                print('error reading', cls.__name__, filename)
                clobber = True
        if clobber:
            print('generate', cls.__name__, path)
            log = cls.generate(tel, period, night, filename=filename, 
                compact=compact,
                clobberHeaderList=clobberHeaderList, path=path, **kwarg)
        log.fix_pids()
        log.fix_targets()
        log.fix_filters()
        if clobber:
            log.write(filename, format=format, **iokwarg) 
            if compact:
                base, ext = os.path.splitext(filename)
                filename = '{}-compact{}'.format(base, ext)
                log.write(filename, format=format, compact=True, **iokwarg)
        return log
    @classmethod
    def empty(cls, tel, period=None, night=None, path='.'):
        log = cls()
    @classmethod
    def generate(cls, tel, period=None, night=None, 
            filename=None, **kwarg):
        raise RuntimeError('generate is implemented for subclasses')
    def sort(self, keys=['night', 'internal', 'ob_start', 'start']):
        index = numpy.argsort(self, order=keys)
        self[:] = self[index]
    def __getitem__(self, i):
        if array(i).dtype.char in 'SU':
            return Table(self, copy=False)[i]
        return super().__getitem__(i) 
    def onsky(self):
        keep =  (self.internal != 1) * (self.obs_type != 'FLAT,SCREEN')
        return self[keep]
    def write(self, fh=None, format= 'ascii.fixed_width_two_line', 
            compact=False, **kwarg):
        if not compact:
            super().write(fh, format=format, **kwarg)
            return
        # Compact table: keep science/night calibrations and try
        # to shorten columns widths
        print('compactify', format)
        key_colnames = self.groups.key_colnames
        log = self.onsky().bin(sort_by_keys=False)
        kwarg['include_names'] = ['night', 'start', 'end', 'tac_pid', 'pid',
                    'pi', 
                    'ins', 'obs_cat', 'obs_type', 'target', 'alpha',
                    'delta', 'filter',
                    'exptime', 'nexp',
                    'time', 'night_time', 'twilight_time', 'dark_time',
                    'night time', 'twilight time', 'dark time'] 
        if len(key_colnames):
            log = log.group_by(key_colnames)
        for col in ['start', 'end']:
            log.columns[col].format = lambda x: x[11:19]
        for col in ['time', 'night_time', 'twilight_time', 'dark_time']:
            log.columns[col].format = '.3f'
            log.columns[col].unit = 'h'
        log.columns['exptime'].format = '.1f'
        log.columns['exptime'].unit = 's'
        log.columns['alpha'].format = '06.0f'
        log.columns['alpha'].unit = 'h'
        log.columns['delta'].format = '+07.0f'
        log.columns['delta'].unit = 'deg'
        for col in log.colnames:
            if '_' in col:
                log.columns[col].name = re.sub('_', ' ', col)
        log.write(fh=fh, format=format, compact=False, **kwarg)
    def bin(self, keys=('period', 'night', 'tac', 'tac_pid', 'ins',
                'target', 'filter'), sort_by_keys=False):
        tab = self.group_by(keys, sort_by_keys=sort_by_keys)
        tab = tab.groups.aggregate(self.aggregate_function)
        return tab
    def aggregate(self, fun):
        rows = [list(fun(col) for col in group.columns.values()) 
                    for group in self.groups]
        return type(self)(rows=rows, meta=self.meta) 
    @staticmethod
    def aggregate_function(col):
        name = col.name
        if name in ['start', 'seeing_start', 'airmass_start']:
            return sorted(col)[0]
        if name in ['end', 'seeing_end', 'airmass_end']:
            return sorted(col)[-1]
        if name in ['ob_start', 'ob_end', 'tpl_start', 'tpl_end',
               'ob_name']:
            if len(numpy.unique(col)) == 1:
                return col[0]
            return 'N/A'
        # If joining observations with CALIB/SCIENCE frame(s) and
        # one acquisition... we want it to to be labelled CALIB/SCIENCE
        if name == 'obs_cat':
            if (col == 'SCIENCE').sum() > 0.49 * len(col):
                return 'SCIENCE'
            elif (col == 'CALIB').sum() > 0.49 * len(col):
                return 'CALIB'
            else:
                return ','.join(numpy.unique(col))
        # These are useful for internal purposes anyway
        if name in ['tplno', 'expno']:
            if len(numpy.unique(col)) == 1:
                return col[0]
            return -1
        # Exposure times, execution times etc. are added
        if name[-4:] == 'time' or name == 'nexp':
            return col.sum() 
        if name in ['internal']:
            return numpy.min(col)
        # String colues (filtres, targets) are concatenated 
        if col.dtype.char in 'SU':
            return ','.join(numpy.unique(col))
        # Other numerical colues are averaged
        return col.mean() 
    def set_exectime(self):
        self.time = time_delta(self.start, self.end)
        self.ob_time = max(time_delta(self.ob_start, self.ob_end), 0)
        self.tpl_time = max(time_delta(self.tpl_start, self.tpl_end), 0)
        if self.ephemeris:
            self.dark_time = 0.
            for s, e in self.dark_hours:
                start, end = max(s, self.start), min(e, self.end)
                self.dark_time += max(time_delta(start, end), 0)
            self.night_time = 0.
            for s, e in self.night_hours:
                start, end = max(s, self.start), min(e, self.end)
                self.night_time += max(time_delta(start, end), 0)
            self.twilight_time = 0.
            for s, e in self.twilight_hours:
                start, end = max(s, self.start), min(e, self.end)
                self.twilight_time += max(time_delta(start, end), 0)
        internal = self.internal == 1
        self.night_time[internal] = 0
        self.twilight_time[internal] = 0
        self.dark_time[internal] = 0
    def info(self):
        return type(self).__name__
    def set_comments(self):
        comments = self.compute_comments()
        self.meta['comments'] = comments 
    def compute_comments(self, time_only=False):
        comments = [self.info(), '']
        if self.ephemeris:
            inter = self.date_interval('night_hours', time_only=time_only)
            comments.append('Astronomical night: {}'.format(inter))
            inter = self.date_interval('twilight_hours', time_only=time_only)
            comments.append('Astronomical twilight: {}'.format(inter))
            inter = self.date_interval('sundown_hours', time_only=time_only)
            comments.append('Sun down: {}'.format(inter))
            inter = self.date_interval('dark_hours', time_only=time_only)
            comments.append('Dark time: {}'.format(inter))
            if hasattr(self, 'fli'):
                comments.append('Moon illumination: {:.0%}'.format(self.fli))
            comments.append('')
        return comments 
    def set_overheads(self, gaptime=0.01):
        indices = array(range(len(self)))
        # Find approximate date for the end of the exposure / ob 
        self['end'] = [add_overhead(d, seconds=t + 30) if c != 'IDLE' else d
            for d, t, c in zip(self['end'], self['read_time'], self['obs_cat'])]
        self['start'] = [s[0:19] for s in self['start']]
        self['tpl_end'] = self['end']
        self['ob_end'] = self['end']
        firstexp = self['expno'] == 1
        self['start'][firstexp] = self['tpl_start'][firstexp] 
        # If there is <1 min difference between end and start
        # of an on-sky OB/template/exposure, fix the (badly estimated)
        # end time.  Do it also for internal observations on the same
        # instrument.
        for internal in [False, True]:
            prevrow = None
            #j = None
            for i in reversed(indices[self['internal'] == internal]):
            #for i in reversed(indices[self['internal'] == internal]):
                row = self[i]
                if prevrow is not None:
                #if j is not None:
                    if row['tpl_start'] == prevrow['tpl_start']:
                        row['end'] = prevrow['start']
                        row['end'] = prevrow['start']
                        row['tpl_end'] = prevrow['tpl_end']
                        row['ob_end'] = prevrow['ob_end']
                    elif row['ob_start'] == prevrow['ob_start']:
                        row['end'] = prevrow['start']
                        row['tpl_end'] = prevrow['tpl_start']
                        row['ob_end'] = prevrow['ob_end']
                    elif not internal or row['ins'] == prevrow['ins']:
                        end, start = row['ob_end'], prevrow['ob_start']
                        dt = time_delta(end, start)
                        if dt < gaptime:
                            row['end'] = prevrow['ob_start']
                            row['tpl_end'] = prevrow['ob_start']
                            row['ob_end'] = prevrow['ob_start']
                prevrow = row
                #j = i 
    def flag_internal_obs(self):
        # Try to find internal calibrations
        #  1. No telescope tracking except when on flat field screen
        #  2. All templates of an OB are internal calibrations
        # Decide that all internal and flat field integration are without
        # tracking, i.e. they are not on-sky obervations.
        missingtcs = self['track'] == 'N/A'
        self['track'][missingtcs] == 'NORMAL'
        internal = (self['track'] == 'OFF') * (self['obs_type'] != 'FLAT,SCREEN') 
        self['target'][internal] = 'INTERNAL'
        self['internal'][internal] = True 
        screen = (self['obs_type'] == 'FLAT,SCREEN')
        self['target'][screen] = 'SCREEN'
        self['track'][screen] = 'OFF'
        internal_type = numpy.atleast_2d(['DARK', 'BIAS', 'FLAT', 'WAVE']).T
        for ob in numpy.unique(self['ob_start']):
            index = self['ob_start'] == ob
            typ = numpy.atleast_2d(self['obs_type'][index])
            if all(numpy.sum(typ == internal_type, axis=0)):
                self['target'][index] = 'INTERNAL'
                self['track'][index] = 'OFF'
                self['internal'][index] = True 
    def fix_pids(self):
        tel = self.meta['telescope']
        for period in numpy.unique(self['period']):
            path = self.get_path(level='base')
            progs = ProgramList(tel, period, path=path)
            for i, row in enumerate(self):
                if row['period'] != period:
                    continue
                pid = row['pid']
                target = row['target']
                date = row['start']
                ins = row['ins']
                if date == 'DUMMY' and row['end'] == 'DUMMY':
                    continue
                p = progs.lookup(pid, target=target, date=date, ins=ins)
                row['pi'] =  p['Surname'] 
                if (p['Name'] not in ['', 'N/A'] 
                        and p['Surname'] not in ['', 'N/A']):
                    row['pi'] = p['Surname'] # + ' ' + p['Name']
                else:
                    row['pi'] = 'N/A'
                row['tac'] = p['TAC'] 
                row['tac_pid'] = p['PID']
                if row['tac_pid'][0:2] == '60' and row['obs_cat'] == 'SCIENCE':
                    row['obs_cat'] = 'CALIB'
    def set_night(self, night):
        if len(self):
            self['night'] = night
            self['period'] = self.night_to_period(night)
    def fix_targets(self):
        if len(self):
            self.target = [re.sub('[_-]([0-9]{1,2}|[UBVRI])$', '', t) 
                    for t in self.target]
    def fix_filters(self):
        if len(self):
            self.filter = [re.sub('^[NMB]B#(.*)_ESO[0-9]+$', '\\1', t)
                    for t in self.filter]
    def total_night_time(self):
        return self.date_interval('night_hours', time_value=True)
    def total_twilight_time(self):
        return self.date_interval('twilight_hours', time_value=True)
    def total_sundown_time(self):
        return self.date_interval('sundown_hours', time_value=True)
    def total_dark_time(self):
        return self.date_interval('dark_hours', time_value=True)
    def summary(self):
        tab = self.bin(['tac', 'tac_pid'], sort_by_keys=True)
        return tab

class SinglePeriodLog(BasicLog):
    def get_period(self):
        return self.meta['period']
    def report_use(self, show=False):
        total = sum(self['time'])
        night = sum(self['night_time'])
        shut = sum(self['exptime']) / 3600.
        rows = [('ALL', 'all', total, night, shut, 0.)]
        categories =  ['SCIENCE', 'CALIB', 'ACQUISITION', 'IDLE']
        instruments = unique(self['ins'])
        for cat in categories:
            log0 = self[self['obs_cat'] == cat]
            total = sum(log0['time'])
            night = sum(log0['night_time'])
            shut = sum(log0['exptime']) / 3600.
            rows.append((cat, 'all', total, night, shut, 0.))
            for ins in instruments:
                noins = ins[0:6] in ['NONE', 'INSCH', 'INSCHA']
                if (cat == 'IDLE' and not noins) or (cat != 'IDLE' and noins):
                    continue
                log1 = log0[log0['ins'] == ins]
                total = sum(log1['time'])
                night = sum(log1['night_time'])
                shut = sum(log1['exptime']) / 3600.
                rows.append((cat, ins, total, night, shut, 0.))
        # Build table in correct order (not alpha)
        use = Table(rows=rows, names=['Category', 'Instrument', 'Total time', 
            'Night time', 'Shutter time', 'Fraction of night'])
        use = use.group_by('Category', sort_by_keys=False)
        for c in use.columns.values():
            if c.name[-4:] == 'time':
                c.unit = 'h'
                c.format = '.1f'
        use.columns['Fraction of night'].format = '.1%'
        total = self.total_night_time()
        for r in use:
            time = r['Night time'] if r['Category'] != 'SCIENCE' else r['Total time']
            r['Fraction of night'] = time / total
        if show:
            use.pprint(show_unit=True)
        return use 
    def report_program_completion(self):
        tel, period = self.telescope, self.get_period()
        path = self.get_path(level='base')
        progs = Table(ProgramList(tel, period, path=path))
        progs['Title'].format = '{:<}'
        # Add time accounting columns
        itime = numpy.argwhere(array(progs.colnames) == 'Hours')[0][0]
        length = len(progs)
        for name in ['Exposure time', 'Night time', 'Twilight time', 
                'Dark time', 'Execution time']:
            col = Column(name=name, dtype=float, length=length, format='{:.1f}')
            progs.add_column(col, index=itime + 1)
        for name in ['Hours']:
            progs[name].format = '.1f'
        for name in ['Last executed']:
            col = Column(name=name, dtype='U19', length=length)
            progs.add_column(col) 
        for name in ['Completion']:
            col = Column(name=name, dtype=float, length=length, format='{:.0%}')
            progs.add_column(col, index=itime + 1)
        summary = self.bin(['tac', 'tac_pid'], sort_by_keys=True)
        # Loop on program rows to add accounting times 
        voidrow = numpy.array(progs[0].as_void())
        voidrow['TAC'] = 'N/A'
        voidrow['PID'] = (' ' * 14) + 'N/A'
        voidrow['Title'] = 'Unidentified programme'
        voidrow['Surname'] = 'N/A'
        voidrow['Instrument'] = 'NONE'
        voidrow['Time-critical'] = ''
        voidrow['Hours'] = 0
        for row in summary:
            pid = row['tac_pid']
            ins = row['ins']
            if pid not in progs['PID']:
                progs.add_row(voidrow.item())
                prow = progs[-1]
                prow['PID'] = pid
                prow['Instrument'] = ins
            else:
                i = numpy.argwhere(pid == progs['PID'])[0][0]
                prow = progs[i]
            prow['Night time'] = row['night_time']
            prow['Exposure time'] = row['exptime'] / 3600.
            prow['Execution time'] = row['time']
            prow['Twilight time'] = row['twilight_time']
            prow['Dark time'] = row['dark_time']
            prow['Last executed'] = row['end']
        # Deal specially with GROND ToO: split between night, twilight,
        # and bright twilight (>-12).  Do some guessing for exposure time.
        itoo = numpy.argwhere(progs['TAC'] == 'ToO')[0][0]
        ntrow = progs[itoo]
        time = ntrow['Execution time']
        nttime = ntrow['Night time']
        twtime = ntrow['Twilight time']
        brtime = time - nttime - twtime
        exptime = ntrow['Exposure time']
        ntrow['Title'] += ' (night time)'
        ntrow['Hours'] = 0.15 * self.total_night_time()
        ntrow['Twilight time'] = 0.
        ntrow['Execution time'] = nttime
        ntrow['Exposure time'] = exptime * (nttime / time)
        progs.insert_row(i + 1, ntrow.as_void())
        twrow = progs[itoo + 1]
        twrow['Title'] += ' (twilight time)'
        twrow['Hours'] = 0.15 * self.total_twilight_time()
        twrow['Dark time'] = 0.
        twrow['Twilight time'] = twtime
        twrow['Night time'] = 0.
        twrow['Execution time'] = twtime
        twrow['Exposure time'] = exptime * (twtime / time)
        progs.insert_row(i + 2, twrow)
        brrow = progs[itoo + 2]
        brrow['Title'] += ' (civil/nautical twilight)'
        brrow['Hours'] = 0.
        brrow['Twilight time'] = 0.
        brrow['Execution time'] = brtime 
        brrow['Exposure time'] = exptime * (brtime / time)
        # Completion of programmes
        completion = progs['Execution time'] / progs['Hours']
        progs['Completion'] = completion
        noalloc = progs['Hours'] <= 0
        progs['Completion'][noalloc] = -1 
        # renaming
        progs['Hours'].name = 'Allocated time'
        for name in ['Allocated time', 'Execution time', 'Dark time', 'Night time', 'Twilight time', 'Exposure time']:
            progs[name].unit = 'h'
            progs[name].format = '.2f'
        progs['Completion'].format = '.0%'
        progs = progs.group_by('TAC', sort_by_keys=False)
        return progs

class NightLog(SinglePeriodLog):
    def __str__(self):
        names = ['period', 'night', 'start', 'end', 'ob_start', 'tpl_start',
            'ins', 'pid', 'target', 'exptime', 'nexp', 'internal']
        cols = [c for c in self.columns.values() if c.name in names]
        subtab = Table(cols)
        return '\n'.join(subtab.pformat(max_lines=55))
    def __repr__(self):
        return str(self.__class__) + '\n' + str(self)
    def get_night(self):
        return self.meta['night']
    def night_start(self):
        return self.meta['night_hours'][0][0]
    def night_end(self):
        return self.meta['night_hours'][0][1]
    def twilight_start(self):
        return self.meta['twilight_hours'][0][0]
    def twilight_end(self):
        return self.meta['twilight_hours'][1][1]
    def sunset(self):
        return self.meta['sundown_hours'][0][0]
    def sunrise(self):
        return self.meta['sundown_hours'][0][1]
    def info(self):
        date, per, tel = self.get_night(), self.get_period(), self.telescope
        return 'Log for night {} (ESO Period {} at {})'.format(date, per, tel)
    def fill_gaps(self):
        if len(self) != 0:
            self.sort()
            self.set_overheads()
            self.insert_acquisition()
            if self.telescope == '2.2m':
                self.insert_focus(pid='60.A-9120(A)', focustime=0.15, 
                        newins='WFI')
                self.insert_inschange(changetime=0.03)
            self.set_overheads()
        self.insert_gap()
        self.set_overheads()
        self.set_exectime()
        self.set_comments()
    @classmethod
    def generate(cls, tel, period=None, night=None, filename=None, 
            clobberLastNights=False, compact=False, path='.',
            clobberHeaderList=False, clobberHeader=False, fileext='.dat',
            verbose=2):
        # Determine whether to download night log again (if recent some
        # archives may be lacking)
        print('generate nightlog', clobberHeader)
        if night is None:
            night = isoformat(lastnight())
        period = cls.night_to_period(night)
        emptylog = cls(tel=tel, period=period, night=night, path=path)
        datalist = emptylog.get_night_list(clobber=clobberHeaderList, 
                    verbose=verbose - 1)
        #if len(datalist) == 0:
        #    datalist = [b'inexistentheader']
        headers = [emptylog.get_header(dataid, clobber=clobberHeader, 
                verbose=verbose - 1) 
                for dataid in datalist]
        # Load from FITS files
        rows = [cls.load_keywords(h) for h in headers]
        # Generate the night
        log = cls(rows=rows, meta=emptylog.meta)
        # Several elements are missing or incorrect: programme IDs observed
        # under "emergency" accounts, target/filtre names, missing 
        # observations (acquisitions, focus and true downtimes)
        log.set_night(night)
        log.flag_internal_obs()
        log.sort()
        #log.fix_pids()
        #log.fix_targets()
        #log.fix_filters()
        log.fill_gaps()
        log.set_night(night)
        return log
    def set_ephemeris(self):
        self.ephemeris = True
        sun = ephem.Sun()
        moon = ephem.Moon()
        obs = ephem.Observer()
        if len(self):
            lon, lat, alt = self['lon'][0], self['lat'][0], self['alt'][0]
        else:
            if self.telescope in ['2.2m', 'NTT', '3.6m']:
                lon, lat, alt = -70.7346, -29.2543, 2350
            else:
                raise RuntimeError('Unimplemented telescope')
        obs.date = parse_date(self.get_night())
        obs.date += 1 - lon / 360
        obs.lon = lon * pi / 180
        obs.lat = lat * pi / 180
        obs.elev = alt
        obs.pressure = 0
        obs.temp = 0
        sun.compute(obs)
        moon.compute(obs)
        # Night
        obs.horizon = '-18:00' 
        ne, ns = [isoformat(f(sun, use_center=True).datetime()) 
                     for f in [obs.next_rising, obs.previous_setting]]
        self.meta['night_hours'] = [(ns, ne)]
        # Astronomical twilight
        obs.horizon = '-12:00'
        te, ts = [isoformat(f(sun, use_center=True).datetime()) 
                     for f in [obs.next_rising, obs.previous_setting]]
        self.meta['twilight_hours'] = [(ts, ns), (ne, te)]
        # Sunrise/Sunset
        obs.horizon = '-2:00' 
        sr, ss = [isoformat(f(sun, use_center=False).datetime()) 
                     for f in [obs.next_rising, obs.previous_setting]]
        self.meta['sundown_hours'] =  [(ss, sr)]
        # Moon
        self.meta['fli'] = moon.moon_phase
        dark = []
        if moon.neverup:
            dark = [(ns, ne)]
        elif not moon.circumpolar:
            obs.date = parse_date(ns)
            # moon
            mr, ms = [isoformat(f(moon, use_center=False).datetime()) 
                     for f in [obs.next_rising, obs.next_setting]]
            self.meta['moon_rise'] = mr
            self.meta['moon_set'] = ms
            if ms < mr:
                ds, de = min(ms, ne), min(mr, ne)
                if ds < de:
                    dark = [(ds, de)]
            else:
                ds1, de1 = ns, min(mr, ne)
                if ds1 < de1:
                    dark = [(ds1, de1)]
                ds2, de2 = min(ms, ne), min(mr, ne)
                if ds2 < de2:
                    dark.append((ds2, de2))
        self.meta['dark_hours'] = dark
    def add_default_row(self, row=None, start=None, end=None, dt=None, pid=None,
                 replace_values=True, target='N/A', ins='NONE',
                 tec='N/A', cat='N/A', typ='N/A', filt='N/A',
                 name='N/A', pi='N/A', nexp=0):
        if row is None:
            row = self.get_defaults()
        self.add_row(row)
        gap = self[-1:]
        if dt is not None:
            start = add_overhead(end, seconds=-3600 * dt)
        if end is not None:
            gap.end, gap.tpl_end, gap.ob_end = end, end, end
        if start is not None:
            gap.start, gap.tpl_start, gap.ob_start = start, start, start
        if pid is None:
            gap.pid, gap.tac_pid = row['pid'], row['tac_pid']
        else:
            gap.pid, gap.tac_pid = pid, pid
        if gap.pid in ['N/A', 'IDLE']:
            gap.tac = 'N/A'
        if replace_values:
            gap.nexp = 0
            gap.pi = pi
            gap.exptime, gap.read_time = 0., 0.
            gap.target, gap.ins = target, ins
            gap.tplno, gap.expno = 1, 0
            gap.obs_tech, gap.obs_cat, gap.obs_type = tec, cat, typ
            gap.filter = filt
            gap.ob_name = name 
    def insert_focus(self, newins='WFI', focustime=0.14, pid='60.A-9120(A)'):
        ins = self.ins
        dt = min(focustime, time_delta(self.ob_end[:-1], self.ob_start[1:])) 
        dt = numpy.hstack([focustime, dt])
        index = (self.track == 'NORMAL') * (ins == newins)
        index[1:] *= (ins[:-1] != newins) * (dt[1:] > 0.75 * focustime)
        twstart, twend = self.twilight_start(), self.twilight_end()
        index *= (self.ob_end > twstart) * (self.ob_start < twend)
        index *= (self.ob_name != 'Focus') 
        end = self.ob_start[index]
        dt = dt[index]
        for r, e, t in zip(self[index], end, dt):
            self.add_default_row(r, end=e, dt=t, cat='ACQUISITION', pid=pid,
                    ins=newins, target='Focus', name='Focus')
        self.sort()
    def insert_acquisition(self):
        obstart = self.ob_start
        index = (self.track != 'OFF') 
        index *= (self.start != obstart) 
        index[1:] *= obstart[1:] != obstart[:-1]
        if not any(index):
            return
        acq = self[index].copy()
        acq.tplno = 1
        acq.expno = 0
        acq.nexp = 0
        acq.end = acq.start
        acq.start = acq.ob_start
        acq.tpl_start = acq.ob_start
        acq.exptime = 0
        acq.readtime = 0
        acq.obs_cat = 'ACQUISITION'
        for r in acq:
            self.add_default_row(r, replace_values=False) 
        self.sort()
    def insert_inschange(self, changetime=0.03):
        index = (self.track == 'NORMAL') 
        dt = min(changetime, time_delta(self.ob_end[:-1], self.ob_start[1:]))
        dt = numpy.hstack([0, dt])
        index[1:] *= self.ins[:-1] != self.ins[1:] 
        index *= dt > 0
        index *= self.obs_tech != 'Instrument change'
        twstart, twend = self.twilight_start(), self.twilight_end()
        index *= (self.ob_end > twstart) * (self.ob_start < twend)
        end = self.ob_start[index]
        dt = dt[index]
        for r, e, t in zip(self[index], end, dt):
            self.add_default_row(r, end=e, dt=t,  
                    pid='IDLE', cat='IDLE', ins='INSCHANGE')
        self.sort()
    def insert_gap(self, gaptime=0.01):
        nstart, nend = self.night_start(), self.night_end()
        # Empty night...
        if len(self) == 0 or all(self.internal):
            self.add_default_row(start=nstart, end=nend, pid='IDLE', cat='IDLE')
            self.track = 'OFF'
            return
        # Don't use internal calibrations
        onsky = self[self['internal'] != 1].copy()
        onsky.sort()
        lastrow = onsky[-1:].copy()[0]
        # Determine the time gap between end of an OB and start
        # of the next one.  Cut-off at twilight, so no gap outside
        # night are reported
        start = max(nstart, numpy.hstack([nstart, onsky.end]))
        end = min(nend, numpy.hstack([onsky.start, nend])) 
        hasgap = time_delta(start, end) >= gaptime
        # Create new rows for each gap
        start = start[hasgap] 
        end = end[hasgap]
        onsky.add_default_row(lastrow)
        gaps = onsky[hasgap]
        gaps.tac = 'N/A'
        gaps.track = 'OFF'
        for s, e, gap in zip(start, end, gaps):
            self.add_default_row(gap, start=s, end=e, pid='IDLE', cat='IDLE')
        self.sort()

class PeriodLog(SinglePeriodLog):
    def night_range(self):
        first = parse_date(self.first_night).date()
        last = parse_date(self.last_processed_night).date()
        date = numpy.hstack([numpy.arange(first, last), last])
        return [str(d) for d in date]
    def set_ephemeris(self):
        period = self.get_period()
        # Determine period boundaries
        y = 1967 + (period + 1) // 2
        m = 4 + 6 * ((period + 1) % 2)
        first = isoformat(datetime.date(y, m, 1))
        y = 1968 + period // 2
        m = 4 + 6 * (period % 2)
        last = datetime.date(y, m, 1) - datetime.timedelta(days=1)
        lastnt = lastnight()
        last_processed = min(last, lastnight())
        self.first_night = str(first)
        self.last_night = str(last)
        self.last_processed_night = str(last_processed)
        # Loop on nights to determine individual nights' ephemeris
        self.dark_hours = []
        self.night_hours = []
        self.twilight_hours = []
        self.sundown_hours = []
        for night in self.night_range():
            log = NightLog(tel=self.telescope, night=night) 
            self.dark_hours += log.dark_hours
            self.night_hours += log.night_hours
            self.twilight_hours += log.twilight_hours
            self.sundown_hours += log.sundown_hours
        self.ephemeris = True
    def info(self):
        tel, period = self.telescope, self.get_period()
        start, end = self.first_night, self.last_night
        return 'Log for ESO period {} at {} ({} to {})'.format(period, tel,
                start, end)
    def compute_comments(self, time_only=True):
        comments = super().compute_comments(time_only=time_only)
        start, last = self.first_night, self.last_processed_night
        comments.append('Based on processed nights: {} to {}'.format(start, last))
        comments.append('')
        return comments
    @classmethod
    def generate(cls, tel, period, night=None, filename=None, compact=False, 
            clobberNightLog=False, clobberLastNights=False, ext='.dat',
            path='.', verbose=2, **kwarg):
        rows = []
        print('generate')
        emptylog = cls(tel=tel, period=period, path=path)
        for night in emptylog.night_range():
            nightlog = NightLog.read(tel, period=period, night=night, 
                    compact=compact, path=path, 
                    clobber=clobberNightLog, 
                    clobberLastNights=clobberLastNights, **kwarg)
            rows += nightlog.as_array().tolist()
        log = PeriodLog(rows=rows, meta=emptylog.meta)
        log.set_comments()
        try:
            log = log.group_by(['period', 'night'])
        except: 
            print('error grouping log')
        return log

        

def retrieve_fits_keywords(filename, keywords):
  if filename[~3:] == '.fits':
    with pyfits.open(filename) as hdulist:
      hdr = hdulist[0].header
  elif filename[~3:] == '.hdr':
    hdr = pyfits.Header.fromtextfile(filename)
  else:
    raise RuntimeError('Unknown file type')
  return [retrieve_fits_keyword(hdr, k[0], k[2]) for k in keywords]


from MPG.programlist import ProgramList
