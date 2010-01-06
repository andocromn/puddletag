#apev2.py

#Copyright (C) 2008-2009 concentricpuddle

#This audio is part of puddletag, a semi-good music tag editor.

#This program is free software; you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation; either version 2 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program; if not, write to the Free Software
#Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from mutagen.monkeysaudio import MonkeysAudio
APEv2File = MonkeysAudio

import util
from util import (strlength, strbitrate, strfrequency, usertags, PATH, isempty,
                getfilename, lnglength, getinfo, FILENAME, INFOTAGS, READONLY)


class Tag(util.MockTag):
    """Tag class for APEv2 files.

    Tags are used as in ogg.py"""
    IMAGETAGS = ()
    def __getitem__(self,key):
        """Get the tag value from self._tags. There is a slight
        caveat in that this method will never return a KeyError exception.
        Rather it'll return an empty string (u'')."""

        try:
            return self._tags[key]
        except KeyError:
            #This is a bit of a bother since there will never be a KeyError exception
            #But its needed for the sort method in tagmodel.TagModel, because it fails
            #if a key doesn't exist.
            return u""

    def __setitem__(self, key, value):
        if key in READONLY:
          return
        if key == FILENAME:
            self.filename = value
            self._tags[FILENAME] = value
            return

        if key not in INFOTAGS and isempty(value):
            del(self[key])

        if key in INFOTAGS or isinstance(key, (int, long)):
          self._tags[key] = value
        elif (key not in INFOTAGS) and isinstance(value, (basestring, int, long)):
            self._tags[key] = [unicode(value)]
        else:
            self._tags[key] = [unicode(z) for z in value]

    def copy(self):
        tag = Tag()
        tag.load(copy(self._mutfile), self._tags.copy())
        return tag

    def delete(self):
        self._mutfile.delete()
        for z in self.usertags:
            del(self._tags[z])

    def _info(self):
        info = self._mutfile.info
        fileinfo = [('Filename', self[FILENAME]),
                    ('Size', unicode(int(self['__size'])/1024) + ' kB'),
                    ('Path', self[PATH]),
                    ('Modified', self['__modified'])]
        apeinfo = [('Frequency', self['__frequency']),
                   ('Channels', unicode(info.channels)),
                   ('Length', self['__length']),
                   ('Version', unicode(info.version))]
        return [('File', fileinfo), ("Monkey's Audio Info", apeinfo)]

    info = property(_info)

    def load(self, mutfile, tags):
        self._mutfile = mutfile
        self.filename = tags[FILENAME]
        self._tags = tags

    def link(self, filename, x = None):
        """Links the audio, filename
        returns self if successful, None otherwise."""
        filename = getfilename(filename)
        audio = APEv2File(filename)
        tags = getinfo(filename)
        self._tags = {}
        if audio is None:
            return

        for z in audio:
            self._tags[z.lower()] = audio.tags[z][:]

        info = audio.info
        self._tags[u"__length"] = strlength(info.length)
        try:
            self._tags[u"__frequency"] = strfrequency(info.sample_rate)
        except AttributeError:
            'No frequency.'
        self._tags.update(tags)
        self.filename = tags[FILENAME]
        self._mutfile = audio
        return self

    def save(self):
        if self.filename != self._mutfile.filename:
            self._mutfile.filename = self.filename
        audio = self._mutfile

        newtag = {}
        for tag, value in usertags(self).items():
            try:
                newtag[tag] = value
            except AttributeError:
                pass
        toremove = [z for z in audio if z not in newtag and audio[z].kind == 0]
        for z in toremove:
            del(audio[z])
        audio.tags.update(newtag)
        audio.save()


filetype = (APEv2File, Tag)