#!/usr/bin/env python2

# LEGACY version. Will not work on a modern machine.

# List, convert, sort, and archive FEROS reduced data for a given night.
# Written by Regis Lachaume after a MIDAS script by Johny Setiawan.
# Public domain.

import pyfits # legacy python on FEROS machine...
import os, re, sys, datetime

FEROSdir = '/data/reduced/FEROS'
PIDdir = '[0-9][0-9]*[A-Z]'

class Midas:
  def __init__(self, session='xx'):
    self.pipe = os.popen('inmidas -p %s >/dev/null' % session, 'w')
  def bdf2fits(self, inname, outname, fitsext='fits', clobber=False):
    if outname is None:
      outname = inname
    try:
      os.stat('%s.%s' % (outname, fitsext))
    except:
      clobber = True
    if clobber:
      self.pipe.write('outdisk/fits %s.bdf %s.%s >/dev/null\n' % (inname, outname, fitsext))

def makedirs(dir):
  try:
    os.makedirs(dir)
  except OSError:
    pass

def obsinfo(file):
  hdr = pyfits.open(file)[0].header
  try:
    pid = hdr['HIERARCH ESO OBS PROG ID']
  except:
    pid = None 
  try:
    targ = hdr['HIERARCH ESO OBS TARG NAME']
  except:
    targ = None
  try:
    tpl = hdr['HIERARCH ESO TPL ID'][10:]
  except:
    tpl = None
  return pid, tpl, targ

class Log(dict):
  def __init__(self, night, datadir=None, log=None):
    self.night = night
    if datadir is None: 
      datadir = FEROSdir + '/' + night 
    self.datadir = datadir
    if log is None:
      files = os.listdir(self.datadir)
      fero = filter(lambda x: re.match('fero[0-9]{4}\.mt', x), files)
      info = map(lambda x: obsinfo(self.datadir + '/' + x), fero)
      frames = map(lambda x: int(re.search('[0-9]{4}', x).group()), fero)
      log = dict(zip(frames, info))
    dict.__init__(self, log)
  
  def keys(self, templates=None):
    keys = dict.keys(self)
    if templates is not None:
      keys =  filter(lambda x: self[x][1] in templates, keys)
    keys.sort()
    return keys
  
  def values(self, templates=None):
    return [self[k] for k in self.keys(templates=templates)]
  
  def __repr__(self):
    str = __name__ + '.Log(\n' 
    str += 'night=' + repr(self.night) + ',\n'
    str += 'datadir=' + repr(self.datadir) + ',\nlog={\n'
    keys = self.keys()
    str += '\n'.join([repr(k) + ': ' + repr(self[k]) + ',' for k in keys])
    str += '\n})'
    return str
  
  def __str__(self):
    str = 'Night: %s\n\n' % self.night 
    str += '%5s %14s %12s %20s\n' % ('Frame', 'Prog. ID', 'Template', 'Target') 
    for frame in self.keys():
      str += ' %04i %14s %12s %20s\n' % ((frame, ) + self[frame])
    return str
  
  def tofits(self, destdir=None, sort=True, templates=['cal_ThAr_Ne', 'obs_objsky', 'obs_objcal'], clobber=False):
    print "Converting and sorting frames for night %s" % self.night
    midas = Midas('xy')
    if destdir is None:
      destdir = self.night
    for frame in self.keys(templates=templates):
      if sort:
        pid, tpl, targ = self[frame]
        pid = re.sub('[()]', '', pid)
        if targ is None:
          targ = tpl
        obdir = '%s/%s/%s' % (destdir, pid, targ)
      print "  %04i -> %s" % (frame, obdir)
      makedirs(destdir)
      for fibre in 1, 2:
        fibredir = "%s/fibre%1i" % (obdir, fibre)
        makedirs(fibredir)
        inbase = "%s/f%04i%1i" % (self.datadir, frame, fibre)
        outbase = "%s/f%04i%1i" % (obdir, frame, fibre)
        midas.bdf2fits(inbase, outbase, clobber=clobber)
        for order in xrange(1, 40):
          inord = "%s%04i" % (inbase, order)
          outord = "%s/f%04i%1i%04i" % (fibredir, frame, fibre, order)
          midas.bdf2fits(inord, outord, clobber=clobber)

def help():
  print '\n%s -- list, convert, or sort FEROS reduced data.\n' % sys.argv[0]
  print 'Syntax\n'
  print '  %s [action1,action2,...] [night]\n' % sys.argv[0]
  print 'Actions\n' 
  print '  list: list frames for the night'
  print '  convert: convert (to FITS) and sort (by programme) lamp and science frames'
  print '  archive: build archive for each programme'
  print '  compress: compress archives'
  print '  clean: remove anything but compressed archives'
  print '  PIpack: equivalent to convert,archive,compress'
  print '  help: print this message\n'
  print '  Default action PIpack gives archives ready to distribute to PIs.'
  print '  If not specified, the current night is used.'
  print '  In a night, frames are processed incrementally at each call of the script.\n'
  print 'Examples\n'
  print '  %s PIpack,clean 2011-12-01\n' % sys.argv[0]
  print '  %s help\n' % sys.argv[0]


def main(actions, night):
  actions = re.sub('PIpack', 'convert,archive,compress', actions)
  actions = actions.split(',') 
  for action in actions:
    if action not in ['help', 'convert', 'archive', 'compress', 'clean', 'list']:
      return False
  if 'list' in actions or 'convert' in actions:
    log = Log(night)
  for action in actions:
    if action in 'convert':
      log.tofits()
    elif action == 'archive':
      print 'Building/updating archives'
      os.system('cd %s; for dir in `ls -d %s`; do tar uf $dir.tar $dir; done' % (night, PIDdir))
    elif action == 'compress':
      print 'Compressing archives'
      os.system('cd %s; for tar in `ls -d %s.tar`; do gzip -c $tar > $tar.gz; done' % (night, PIDdir))
    elif action == 'list':
      print str(log)
    elif action == 'clean':
      print 'Cleaning...'
      os.system('cd %s; rm -rf %s %s.tar' % (night, PIDdir, PIDdir))
    elif action == 'help':
      help()
  return True

if __name__ == "__main__":
  if len(sys.argv) <= 3:
    if len(sys.argv) == 1:
      actions = 'PIpack'
    else:
      actions = sys.argv[1]
    if len(sys.argv) <= 2:
      midday = datetime.datetime.now() - datetime.timedelta(hours=12)
      night = midday.isoformat()[0:10]
    else:
      night = sys.argv[2]
    ok = main(actions, night)
  else:
    ok = False
  if not ok:
    print "Syntax Error. Type `%s help' for help."
