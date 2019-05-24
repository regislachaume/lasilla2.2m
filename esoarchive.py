import urllib
import urllib.request

class NightRequest:
    def __init__(self, night, inslist, output='html',
            mirror='http://archive.eso.org', max_rows_returned=999999,
            **kwarg):
        self.baseurl = mirror + '/wdb/wdb/eso/eso_archive_main/query'
        inslist = ["(ins_id like '{0}%')".format(i) for i in inslist]
        insquery = '(' + ' or '.join(inslist)  + ')'
        self.form = urllib.parse.urlencode({
            'night': night, 'add': insquery,
            'wdbo': output, 'max_rows_returned': max_rows_returned, **kwarg
        })
    def url(self):
       return self.baseurl + '?' + self.form
    def urlopen(self, encode='utf-8'):
        form = self.form.encode(encode) 
        ok = False
        while not ok:
           try:
                result = urllib.request.urlopen(self.baseurl, form)
                ok = True
           except urllib.error.URLError as error:
                if error.errno != 110:
                     raise error
        return result
