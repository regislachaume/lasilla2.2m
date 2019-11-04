from sys import stdout
from html import escape, unescape

import sys
import os
from numpy import argwhere, size, array, zeros, cumsum
from astropy import table
from astropy.io import ascii, registry 
from astropy.io.ascii import html, fixedwidth, core
from astropy.utils.xml.writer import XMLWriter
from astropy.table.column import pprint, BaseColumn, Quantity
from astropy.table import TableGroups, Column
from astropy.units import UnitBase

FORMATTER = pprint.TableFormatter()
def col_iter_str_vals(col):
    parent_table = col_getattr(col, 'parent_table', None)
    formatter = FORMATTER if parent_table is None else parent_table.formatter
    _pformat_col_iter = formatter._pformat_col_iter
    for str_val in _pformat_col_iter(col, -1, False, False, {}):
        yield str_val

COLUMN_ATTRS = set(['name', 'unit', 'dtype', 'format', 'description', 'meta', 'parent_table'])
def col_getattr(col, attr, default=None):
    if attr not in COLUMN_ATTRS:
        raise AttributeError("attribute must be one of {0}".format(COLUMN_ATTRS))

    # The unit and dtype attributes are considered universal and do NOT get
    # stored in _astropy_column_attrs.  For BaseColumn instances use the usual setattr.
    if (isinstance(col, BaseColumn) or
            (isinstance(col, Quantity) and attr in ('dtype', 'unit'))):
        value = getattr(col, attr, default)
    else:
        # If col does not have _astropy_column_attrs or it is None (meaning
        # nothing has been set yet) then return default, otherwise look for
        # the attribute in the astropy_column_attrs dict.
        if getattr(col, '_astropy_column_attrs', None) is None:
            value = default
        else:
            value = col._astropy_column_attrs.get(attr, default)
        # Weak ref for parent table
        if attr == 'parent_table' and callable(value):
            value = value()
        # Mixins have a default dtype of Object if nothing else was set
        if attr == 'dtype' and value is None:
            value = np.dtype('O')
    return value

def default_format(x):
    t = x.dtype 
    if t.char in 'SU':
        return '{{:<{}}}'.format(t.itemsize // t.alignment)
    else:
        return '{}'


class AsciiWithGroupsData(fixedwidth.FixedWidthTwoLineData):
    repeat_string = '='
    def __init__(self, *arg, **kwarg):
        super().__init__(*arg, **kwarg)
        self.sort_key_nums = []
    def get_str_vals(self):
        prevline = None
        row = 0
        self.indices = [0]
        for line in super().get_str_vals():
            # if it is a group separator (----), a new group is started. 
            # Skip this line (no data) and state no previous line.  
            is_group_sep = all([all(array(list(el)) == '-') for el in line])
            if is_group_sep:
                if prevline:
                    self.indices.append(row)
                    prevline = None
                continue
            # If no previous line (start of the group), we don't
            # process and the line is yielded as is.  If previous line
            # we need repeated items (")... else we're seeing a header
            if prevline is not None:
                repeats = [el == self.repeat_string for el in line]
                group = any(repeats)
                if any(repeats):
                    # Keep track of the columns with repeated elements,
                    # those are the sorted keys
                    self.sort_key_nums = list(argwhere(repeats)[:,0])
                    line = [el if el != self.repeat_string else pel 
                        for el, pel in zip(line, prevline)] 
                    prevgroup = group
                else:
                    # No repeated elements in this line after a previous
                    # one means, we are changing group.  Skip the repeated 
                    # header and store.
                    self.indices.append(row)
                    prevline = None
                    continue
            row += 1
            yield line
            prevline = line
        self.indices.append(row)
        self.indices = array(self.indices)
    def str_vals(self):
        self._set_fill_values(self.cols)
        self._set_col_formats()
        groups =  self.cols[0].parent_table.groups
        sort_keys = groups.key_colnames
        indices = groups.indices[:-1]
        for col in self.cols:
            vals = list(col_iter_str_vals(col))
            if col.name in sort_keys:
                new_vals = [self.repeat_string] * len(vals)
                for i in indices:
                    new_vals[i] = vals[i]
                vals = new_vals
            col.str_vals = vals
        self._replace_vals(self.cols)
        return [col.str_vals for col in self.cols]
 
class AsciiWithGroups(ascii.FixedWidthTwoLine):
    """Fixed wdith table with two header lines and row groups.

    """
    _format_name = 'ascii_with_groups'
    _description = 'Fixed width ascii table handling row groups'
    data_class = AsciiWithGroupsData
    def init(self, *arg, repeat_header=True, **kwarg):
        super().__init__(self, *arg, **kwarg)
        self.repeat_header = repeat_header
    def write(self, table):
        lines = super().write(table)
        if len(table.groups.indices) == 2:
            return lines 
        nstart = len(lines) - len(table)
        indices = [nstart + i for i in table.groups.indices[1:]] 
        if self.repeat_header:
            header = lines[nstart-2:nstart]
        else:
            header = lines[nstart-1:nstart]
        i1 = indices[0] 
        new_lines = lines[0:i1] # table with header and first group
        for i2 in indices[1:]:
            new_lines += header
            new_lines += lines[i1:i2]
            i1 = i2
        return new_lines
    def read(self, table):
        table = super().read(table)
        names = [table.colnames[int(num)] for num in self.data.sort_key_nums]
        if len(names):
            indices = self.data.indices
            keys = table[names][indices[:-1]]
            keys.meta['grouped_by_table_cols'] = True
            groups = TableGroups(table, indices=indices, keys=keys)
            table._groups = groups
        return table

class HTMLWithGroupsDataSplitter(html.HTMLSplitter):
    def __call__(self, lines):
        for line in lines: 
            if not isinstance(line, html.SoupString): 
                raise TypeError('HTML lines should be of type SoupString') 
            soup = line.soup                                            
            # If header is duplicated, don't return it as data!
            header_elements = soup.find_all('th')                       
            if header_elements:                                         
                continue
            data_elements = soup.find_all('td')                         
            if data_elements:                                           
                # Return multirows as a couple for HTMLWithGroupsData handling
                yield [(el.text.strip(), int(el['rowspan']))
                        if el.has_attr('rowspan')
                        else el.text.strip() for el in data_elements]
        if len(lines) == 0:                     
            raise core.InconsistentTableError('HTML tables must contain data '                        'in a <table> tag')   

class HTMLWithGroupsData(html.HTMLData):
    splitter_class = HTMLWithGroupsDataSplitter
    def get_str_vals(self):
        # If rowspan is given by (element, nrows), the following rows
        # must insert the spanned values
        prevspan = None
        for i, line in enumerate(super().get_str_vals()):
            data = [el[0] if size(el) > 1 else el for el in line] 
            span = [el[1] if size(el) > 1 else 0.0 for el in line]
            if i > 0 and any(prevspan):
                span = span[::-1]
                span = [s - 1 if s > 1 else span.pop() for s in prevspan]
                data = data[::-1]
                newdata = [e if s > 1 else data.pop() 
                        for e, s in zip(prevdata, prevspan)]
                prevdata = newdata
                data = newdata + data[::-1] # too many columns?
            else:
                prevdata = data
            prevspan = span
            yield data 

class HTMLWithGroupsInputter(html.HTMLInputter):
   # Need to copy all this for one single bloody line, not very
   # well though astropy...
   def process_lines(self, lines):
        """
        Convert the given input into a list of SoupString rows
        for further processing.
        """

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise core.OptionalTableImportError('BeautifulSoup must be '
                                        'installed to read HTML tables')

        if 'parser' not in self.html:
            soup = BeautifulSoup('\n'.join(lines))
        else: # use a custom backend parser
            soup = BeautifulSoup('\n'.join(lines), self.html['parser'])
        tables = soup.find_all('table')
        for i, possible_table in enumerate(tables):
            if html.identify_table(possible_table, self.html, i + 1):
                table = possible_table # Find the correct table
                break
        else:
            if isinstance(self.html['table_id'], int):
                err_descr = 'number {0}'.format(self.html['table_id'])
            else:
                err_descr = "id '{0}'".format(self.html['table_id'])
            raise core.InconsistentTableError(
                'ERROR: HTML table {0} not found'.format(err_descr))

        self.html['attrs'] = table.attrs
        # Get all table rows
        soup_list = [html.SoupString(x) for x in table.find_all('tr')]

        return soup_list


class HTMLWithGroups(html.HTML):
    """HTML table with row groups"""
    data_class = HTMLWithGroupsData
    inputter_class = HTMLWithGroupsInputter
    _format_name = 'html_with_groups'
    _description = 'HTML table handling row groups'
    def write_header(self, writer, cols, sort_keys=[]):
        with writer.tag('tr'):
            for col in cols:
                kwarg = {}
                if  len(col.shape) > 1 and self.html['multicol']:
                    kwarg['colspan'] = col.shape[1]
                name = col_getattr(col, 'name')
                writer.element('th', name.strip(), **kwarg)
        if self.show_units:
            with writer.tag('tr'):
                for col in cols:
                    kwarg = {}
                    if  len(col.shape) > 1 and self.html['multicol']:
                        kwarg['colspan'] = col.shape[1]
                    unit = col_getattr(col, 'unit')
                    if unit is None:
                        unit = ''
                    if isinstance(unit, UnitBase):
                        unit = unit.names[0]
                    writer.element('th', unit.strip(), **kwarg)
    def write_body(self, writer, cols, sort_keys=[]):
        col_str_iters = []
        for col in cols:
            if len(col.shape) > 1 and self.html['multicol']:
                span = col.shape[1]
                for i in range(span):
                    subcol = table.Column([el[i] for el in col])
                    subcol = col_iter_str_vals(subcol)
                    col_str_iters.append(col_iter_str_vals(subcol))
            else:
                col_str_iters.append(col_iter_str_vals(col))
        nrows = cols[0].size
        tr_attr_fun = self.html.get('tr_attr_fun', lambda row: {})
        td_attr_fun = self.html.get('td_attr_fun', lambda name, el: {})
        for i, row in enumerate(zip(*col_str_iters)):
            tr_attr =  tr_attr_fun(row)
            with writer.tag('tr', attrib=tr_attr):
                for el, col in zip(row, cols):
                    el = el.strip()
                    td_attr = td_attr_fun(col.name, el)
                    if col.name in sort_keys and nrows > 1:
                        if i > 0:
                            continue
                        td_attr['rowspan'] = col.size
                    writer.element('td', el, attrib=td_attr)
    def __init__(self, htmldict={}, repeat_header=True):
        self.repeat_header = True
        super().__init__(htmldict=htmldict)
    def write(self, tab):
        lines = []
        writer = XMLWriter(html.ListWriter(lines))
        cols = tab.columns.values()
        sort_keys = tab.groups.key_colnames
        tableattr = self.html.get('table_attr', {})
        id = self.html['table_id'] 
        if isinstance(id, str):
            tableattr['id'] = id
        if len(sort_keys):
            tableattr['data-sort-keys'] = escape(','.join(sort_keys))
        with writer.tag('table', tableattr):
            if 'caption' in self.html:
                writer.element('caption', self.html['caption'])
            for i, g in enumerate(tab.groups):
                cols = g.columns.values() 
                if self.include_names is not None:
                    cols = [col for col in cols if col.name in self.include_names]
                if self.exclude_names is not None:
                    cols = [col for col in cols if not col.name in self.exclude_names]
                if i == 0:
                    with writer.tag('thead'):
                        self.write_header(writer, cols, sort_keys=sort_keys)
                with writer.tag('tbody'):
                    if i > 0 and self.repeat_header:
                        self.write_header(writer, cols, sort_keys=sort_keys)
                    self.write_body(writer, cols, sort_keys=sort_keys)
        return [''.join(lines)]
    def read(self, table):
        # bug
        table = super().read(table)
        attrs = self.inputter.html['attrs']
        # sort (inefficient, should build groups)
        if 'data-sort-keys' in attrs:
            sort_keys = unescape(attrs['data-sort-keys']).split(',')
            table = table.group_by(sort_keys)
        return table


class Table(table.Table):
    def write(self, output=None, *arg, fast_writer=True, 
            format='ascii.ascii_with_groups', repeat_header=True, 
            show_units=False, **kwargs):
        from astropy.io.ascii.ui import _get_format_class, get_writer
        if format[0:6] == 'ascii.':
            format = format[6:]
        if output is None:
            output = sys.stdout
        if self.has_mixin_columns:
            fast_writer = False
        print('Table Writer ... ', format)
        Writer = _get_format_class(format, None, 'Writer')
        writer = get_writer(Writer=Writer, fast_writer=fast_writer, **kwargs)
        writer.repeat_header = repeat_header
        writer.show_units = show_units
        if writer._format_name in core.FAST_CLASSES:
            writer.write(self, output)
            return
        lines = writer.write(self)
        # Write the lines to output
        outstr = os.linesep.join(lines)
        if not hasattr(output, 'write'):
            print('output', output)
            output = open(output, 'w')
            output.write(outstr)
            output.write(os.linesep)
            output.close()
        else:
            output.write(outstr)
            output.write(os.linesep)
    @    classmethod
    def read(cls, *arg, format='ascii.ascii_with_groups', **kwargs):
        tab = table.Table.read(*arg, format=format, **kwargs)
        tab.__class__ = cls
        return tab
    def _get_colnames(self):
        return self.__dict__.get('columns', {}).keys()
    def _get_meta(self):
        return self.__dict__.get('_meta', {})
    def __getattr__(self, a):
        if a in self._get_colnames():
            return super().__getitem__(a)
        meta = self._get_meta()
        if a in meta:
            return meta[a]
        err = '{} has no attribute {}'.format(type(self).__name__, a)
        raise AttributeError(err)
    def __setattr__(self, a, v):
        if a[0] == '_' or a in self.__dict__ or a in ['columns', 'formatter', 'meta']:
            super().__setattr__(a, v)
        elif a in self._get_colnames():
            super().__setitem__(a, v)
        else:
            meta = self._get_meta()
            meta[a] = v
    def group_by(self, keys, sort_by_keys=True):
        if keys == []:
            tab = self.copy()
            if len(tab.groups) > 1:
                del tab._groups
            return tab
        if sort_by_keys:
            tab = super().group_by(keys)
            tab.groups.keys.meta['sorted_by_keys'] = True
            return tab
        bycolnames = False
        if isinstance(keys, str):
            keys = (keys,)
        if isinstance(keys, (list, tuple)):
            keys = self[keys]
            bycolnames = True
        sort_keys = zeros((len(self),), dtype=int)
        sort_keys[1:] = cumsum(keys[1:] != keys[:-1]) 
        cls = type(self)
        tab = table.Table(self).group_by(sort_keys)
        tab.__class__ = cls
        keys.meta['sorted_by_keys'] = False
        keys.meta['grouped_by_table_cols'] = bycolnames
        tab.groups._keys = keys
        return tab
    def __repr__(self):
        name = '{}.{}'.format(type(self).__module__, type(self).__name__)
        r, c = len(self), len(self.colnames)
        id_ = hex(id(self))
        m = ''
        if self.masked:
            m = ', masked'
        return '<{} at {} ({}R x {}C{})>'.format(name, id_, r, c, m)
    def __init__(self, *arg, rows=None, **kwarg):
        if rows == []:
            rows = None
        self.meta['primary_key'] = None
        super().__init__(*arg, rows=rows, **kwarg)
    
        
if __name__ == "__main__":
    from astropy.io.registry import get_reader, get_writer
    from sys import stdout
    tab = Table.read('table.txt', format='ascii')
    srt = tab.group_by('foo')
    srt.write('table-grouped.txt')
    srtnew = Table.read('table-grouped.txt')
    #areader = AsciiWithGroups()
    #asc =  areader.write(srt)
    #srt2 = areader.read(asc)
    #print('\n'.join(asc))
