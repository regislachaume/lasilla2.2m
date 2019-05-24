import ephem
import datetime
import configparser
import numpy
import xlrd
import os
import argparse

def argparser(description, wwwsubdir=''):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--local-dir', dest='dir',
        help='Root directory for night log system',
        default='/home/lachaume/Work/2.2m/nightlogs')
    parser.add_argument('--telescope', dest='tel',
        help='ESO telescope',
        action='store', default='2.2m')
    parser.add_argument('--publish', action='store_true', default=False,
        help='Publish to web-site')
    parser.add_argument('--remote-dir', dest='rdir',
        help='Remote directory for web publishing',
        action='store', 
        default='lachaume@black.astro.puc.cl:.www/2.2m/' + wwwsubdir)

    return parser

def get_sun(date, twilight='astronomical'):
    obs = ephem.Observer()
    obs.date = date
    obs.lon = '-70.729166667'
    obs.lat = '-29.256666666'
    obs.date += 1 - float(obs.lon) / 360
    #obs.elev = 2347.
    obs.horizon = '-02:00' # 18 * pi / 180
    obs.pressure = 0 # 760
    obs.temp = 15
    sun = ephem.Sun()
    sun.compute(obs)
    srise = obs.next_rising(sun).datetime()
    sset = obs.previous_setting(sun).datetime()
    obs.pressure = 0
    if twilight == 'astronomical':
      obs.horizon = '-18:00' # * pi / 180
    elif twilight == 'nautical':
      obs.horizon = '-12:00'
    else:
      obs.horizon = '-06:00'
    twend =  obs.previous_setting(sun, use_center=True).datetime()
    twbegin = obs.next_rising(sun, use_center=True).datetime()
    return (sset, twend, twbegin, srise)


def load_config(tel, period, path='.'):
    from MPG.esolog import BasicLog
    path = BasicLog(tel=tel, period=period, path=path).get_path()
    configfile = 'config-{}-P{}.conf'.format(tel, period)
    configfile = os.path.join(path, configfile)
    config = configparser.ConfigParser(delimiters=('=',))
    config.read([configfile])
    return config


def get_period_limits(p):
    p = int(p)
    y = 1967 + (p + 1) // 2
    m = 4 + 6 * ((p + 1) % 2)
    begin = datetime.date(y, m, 1)
    y = 1968 + p // 2
    m = 4 + 6 * (p % 2)
    day = datetime.timedelta(days=1)
    end = datetime.date(y, m, 1) - day
    return begin, end

def iter_period_dates(p):
    begin, end = get_period_limits(p)
    date = begin
    day = datetime.timedelta(days=1)
    while date <= end:
        yield date
        date += day     

def structured_array(records=None, cols=None, names=None, dtypes=None,
                     cls=numpy.ndarray):
    if cols == None:
        cols = [c for c in zip(*records)]
        if names is None:
            names = records[0].dtype.names
    if dtypes == None:
        dtypes = [None for c in cols]
    cols = [numpy.asarray(c, dtype=t) for c, t  in zip(cols, dtypes)]
    dtype = [(n, c.dtype) for n, c in zip(names, cols)]
    shape = (len(cols[0]),)
    arr = numpy.ndarray(shape=shape, dtype=dtype)
    for n, c in zip(names, cols):
        arr[n] = c
    arr = arr.view(type=cls, dtype=(numpy.record, arr.dtype))
    return arr

def structured_array_from_excel(filename, start_row=0, start_col=0,
                                layout='vertical', cls=numpy.recarray,
                                sheetnum=0):
    with xlrd.open_workbook(filename) as book:
        page = book.sheets()[sheetnum]
    ncols, nrows = page.ncols, page.nrows
    cols = []
    records, dtype = [], []
    if layout in ['vertical', 'columns']:
        names = page.row_values(start_row, start_col, ncols)
        cols = [page.col_values(c, start_row + 1, nrows)
                              for c in range(start_col, ncols)]
    else:
        names = page.col_values(start_col, start_row, nrows)
        cols = [page.col_values(r, start_col + 1, ncols)
                              for r in range(start_row, nrows)]
    return structured_array(cols=cols, names=names, cls=cls)

