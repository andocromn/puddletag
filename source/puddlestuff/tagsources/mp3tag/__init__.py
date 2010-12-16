# -*- coding: utf-8 -*-
from pyparsing import QuotedString, Word, nums, printables, Optional, Combine
import re, pdb, os

import sys, traceback

from puddlestuff.util import convert_dict as _convert_dict
from puddlestuff.tagsources import (urlopen, get_encoding,
    write_log, retrieve_cover)
from puddlestuff.constants import CHECKBOX
from funcs import FUNCTIONS
from copy import deepcopy
import codecs
from htmlentitydefs import name2codepoint as n2cp

class ParseError(Exception): pass

def unquote(s, loc, tok):
    """Doing this manually, because QuotedString's method removes \'s from
    regular expressions."""
    tok = tok.pop()[1:-1]
    return tok.replace('\\"', '"')

def getnum(s, l,t):
    return int(''.join(t))

STRING = QuotedString('"', '\\', unquoteResults=False).setParseAction(unquote)
NUMBER = Combine(Optional('-') + Word(nums)).setParseAction(getnum)
COVER = '#cover-url'

ARGUMENT = STRING | NUMBER
ARGUMENT.ignore(u'#' + Word(printables))

MTAG_KEYS = {
    '_length': '__length',
    '_url': '#url',
    'coverurl': COVER,
    'publisher': 'label',
    'track temp': 'track'}

def convert_entities(s):
    s = re.sub('&#(\d+);', lambda m: unichr(int(m.groups(0)[0])), s)
    return re.sub('&(\w)+;',
        lambda m: n2cp.get(m.groups(0), u'&%s;' % m.groups(0)[0]), s)
    

def convert_value(value):
    value = filter(None, (z.strip() for z in value.split(u'|')))
    value = [convert_entities(v.replace(u'\\r\\n', u'\n')) for v in value]
    if len(value) == 1:
        return value[0]
    return value

def convert_dict(d, keys = MTAG_KEYS):
    d = dict((i,z) for i,z in ((k.lower(), convert_value(v)) for
        k,v in d.iteritems()) if z)
    return _convert_dict(d, keys)

def find_idents(lines):
    ident_lines = {}
    idents = {}
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith(u'['):
            name, value = parse_ident(line)
            idents[name.lower()] = value
            ident_lines[i] = name.lower()
        elif not line or line.startswith(u'#'):
            continue

    values = sorted(ident_lines)
    max_val = max(values)
    for i, (lineno, ident) in enumerate(sorted(ident_lines.items())):
        if ident == 'parserscriptindex':
            if lineno < max_val:
                search_source = (lineno, lines[lineno + 1: values[i+1]])
            else:
                search_source = (lineno, lines[lineno + 1:])
        elif ident == 'parserscriptalbum':
            if lineno < max_val:
                album_source = (lineno, lines[lineno + 1: values[i+1]])
            else:
                album_source = (lineno, lines[lineno + 1:])

    try:
        offset = search_source[0]
    except:
        raise ParseError('No search section found.')
    #Adding 2 to offset, because it's needed. I'm to lazy to go search for
    #why it is so.
    search_source = [(offset + i + 2, s) for i, s in
        enumerate(search_source[1])]

    offset = album_source[0]
    album_source = [(offset + i + 2, s) for i, s
        in enumerate(album_source[1])]

    parser = lambda arg: parse_func(*arg)
    return (idents, filter(None, map(parser, search_source)),
        filter(None, map(parser, album_source)))

def open_script(filename):
    f = codecs.open(filename, 'r', encoding='utf8')
    idents, search, album = find_idents(f.readlines())
    return idents, search, album

def parse_album_page(page, album_source, url=None):
    cursor = Cursor(page, album_source)
    if url:
        cursor.output = {'CurrentUrl': url}
    cursor.parse_page()
    info = convert_dict(cursor.album)
    if hasattr(cursor.tracks, 'items'):
        tracks = []
        for field, values in cursor.tracks.iteritems():
            values = convert_value(values)
            if tracks:
                for d, v in zip(tracks, values):
                    d[field] = v
            else:
                tracks = [{field: v} for v in values]
    else:
        tracks = filter(None, map(convert_dict, cursor.tracks))
    return (info, tracks)

def parse_func(lineno, line):
    line = line.strip()
    funcname = line.split(' ', 1)[0].strip()
    args = [z[0] for z in
    ARGUMENT.searchString(line[len(funcname):]).asList()]
    if funcname and not funcname.startswith(u'#'):
        return funcname, lineno, args

def parse_ident(line):
    ident, value = re.search('^\[(\w+)\]=(.*)$', line).groups()
    return ident, value

def parse_lines(lines):
    for line in lines:
        if line.startswith('['):
            print parse_ident(line)
        else:
            print parse_func(line)

def parse_search_page(indexformat, page, search_source, url=None):
    fields = [z[1:-1] for z in indexformat.split('|')]
    cursor = Cursor(page, search_source)
    if url:
        cursor.output = {'CurrentUrl': url}
    cursor.parse_page()

    i = 0
    values = cursor.cache.split('\n')
    albums = []
    exit_loop = False
    max_i = len(values) - 1
    for cached in values:
        values = [z.strip() for z in cached.split('|')]
        album = dict(zip(fields, values))
        albums.append(album)
    return filter(None, map(convert_dict, albums))

class Cursor(object):
    def __init__(self, text, source_lines):
        self.text = text
        self.all_lines = [z + u' ' for z in text.split('\n')] + [u' ']
        self.all_lowered = [z.lower() for z in self.all_lines]
        self._lineno = 0
        self.charno = 0
        self.cache = u''
        self.source = source_lines
        self.debug = False
        self._field = ''
        self.tracks = []
        self.album = {}
        self.num_loop = 0
        self.output = self.album
        self.stop = False

    def _get_char(self):
        return self.line[self.charpos]

    char = property(_get_char)

    def _get_debug_file(self):
        return self._debug_file

    def _set_debug_file(self, filename):
        if not filename:
            self._debug_file = None
            return
        f = open(filename, 'w')
        self._debug_file = f

    debug_file = property(_get_debug_file, _set_debug_file)

    def _get_field(self):
        return self._field

    def _set_field(self, value):
        self.output[self._field] = self.cache
        self.cache = self.output.get(value, u'')
        self._field = value

    field = property(_get_field, _set_field)

    def _get_lineno(self):
        return self._lineno

    def _set_lineno(self, value):
        self._lineno = value
        try:
            self.line = self.all_lines[self.lineno]
        except IndexError:
            self.stop = True
            

    lineno = property(_get_lineno, _set_lineno)

    def _get_lines(self):
        return self.all_lines[self.lineno:]

    lines = property(_get_lines)

    def _get_lowered(self):
        return self.all_lowered[self.lineno:]

    lowered = property(_get_lowered)

    def log(self, text):
        if self.debug and self.debug_file:
            self._debug_file.write((u'\n' + text).encode('utf8'))
            self._debug_file.flush()
        elif self.debug:
            print text

    def parse_page(self):
        self.next_cmd = 0
        self.cmd_index = 0
        i = 1

        while (not self.stop) and (self.next_cmd < len(self.source)):

            self.log(unicode(self.output))
            cmd, lineno, args = self.source[self.cmd_index]
            
            self.log(unicode(self.source[self.cmd_index]))
            
            #if i >= 26 and lineno >= 73:
                #print cmd, lineno, args
                #pdb.set_trace()
            #elif lineno == 30:
                #i += 1
            
            if not FUNCTIONS[cmd](self, *args):
                self.next_cmd += 1
            self.cmd_index = self.next_cmd

        self.output[self.field] = self.cache
        
        if self.output is not self.album:
            try:
                self.tracks.append(self.output)
            except AttributeError:
                self.tracks.update(self.output)
        self.stop = False

    def to_command(self, name):
        for i, l in enumerate(self.source[self.lineo:]):
            if l.startswith(command):
                self.lineno = self.lineno + i
                return True
        return False

class Mp3TagSource(object):
    def __init__(self, idents, search_source, album_source):

        self._get_cover = True
        self.preferences = [
            ['Retrieve Covers', CHECKBOX, self._get_cover]]

        self.search_source = search_source
        self.album_source = album_source
        self._search_base = idents['indexurl']
        self._separator = idents['wordseperator']
        self.group_by = [idents['searchby'][1:-1], None]
        self.name = idents['name'] + u' (Mp3tag)'
        self.indexformat = idents['indexformat']
        self.album_url = idents['albumurl']
        self.tooltip = tooltip = """<p>Enter search keywords here. If empty,
        the selected files are used.<br /><br />
        Searches are done by <b>%s</b></p>""" % self.group_by[0]

    def applyPrefs(self, args):
        self._get_cover = args[0]

    def keyword_search(self, text):
        return self.search(text)

    def search(self, artist, files=None):
        artist = re.sub('\s+', self._separator, artist)
        url = self._search_base % artist
        write_log(u'Opening Search Page: %s' % url)
        page = get_encoding(urlopen(url), True, 'utf8')[1]
        infos = parse_search_page(self.indexformat, page, self.search_source, url)
        return [(info, []) for info in infos]

    def retrieve(self, info):
        info = deepcopy(info)
        url = self.album_url + info['#url']
        write_log(u'Opening Album Page: %s' % url)
        page = get_encoding(urlopen(url), True, 'utf8')[1]
        new_info, tracks = parse_album_page(page, self.album_source, url)
        info.update(new_info)
        if self._get_cover and COVER in info:
            cover_url = new_info[COVER]
            if isinstance(cover_url, basestring):
                info.update(retrieve_cover(cover_url))
            else:
                info.update(map(retrieve_cover, cover_url))
        return info, tracks

if __name__ == '__main__':
    #text = open(sys.argv[1], 'r').read()
    text = open(sys.argv[1], 'r').read()
    import puddlestuff.tagsources
    encoding, text = puddlestuff.tagsources.get_encoding(text, True, 'utf8')

    #pdb.set_trace()
    idents, search, album = open_script(sys.argv[2])
    value = parse_search_page(idents['indexformat'], text, search)
    
    #value = parse_album_page(text, album, 'url')
    print value
    pdb.set_trace()
    print convert_value(value)
    #source = find_idents(lines)[1]
    
    #print parse_search(idents['indexformat'], search, text)
    ##text = open('d_album.htm', 'r').read()
    #c = Cursor(text.decode('utf8', 'replace'), source)
    #c.parse_page()
    ##print c.cache
    ##print c.tracks[0]
    #print u'\n'.join(u'%s: %s' % z for z in c.album.items())
    