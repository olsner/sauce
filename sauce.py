#!/usr/bin/env python
#
# Copyright (c) 2012 Simon Brenner
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# vim:et:

class Section(object):
    def __init__(self, name):
        self.name = name
        self.start = None
        self.end = None
        self.size = None

    def __repr__(self):
        return "%s: %x..%x" % (self.name, self.start, self.end)

class Line(object):
    def __init__(self, file, line):
        self.file = file
        self.line = line
        self.total = 0
        self.places = []

    def add(self, offset, length):
        self.total += length
        self.places += [(offset,length)]

    def uri(self):
        return self.file.uri

class File(object):
    def __init__(self, uri):
        self.uri = uri
        self.lines = {}
        self.total = 0

    def add(self, line, offset, length):
        #print '%x..%x: %s:%d' % (offset, offset + length, self.uri, line)
        line = self.lines.setdefault(line, Line(self, line))
        line.add(offset, length)
        self.total += length
        return line

    def getLines(self):
        return sorted(self.lines.items(), key = lambda (i,l): l.total, reverse = True)

    def getTotal(self):
        return self.total

    def getTotalPlaces(self):
        return sum(map(lambda l: len(l.places), self.lines.values()))

    def __str__(self):
        return "File(%s,%d bytes in %d lines)" % (self.uri, self.total, len(self.lines))

    def __repr__(self):
        return "File(%s,%d bytes in %d lines)" % (repr(self.uri), self.total, len(self.lines))

def isint(s):
    try: int(s); return True
    except: return False

def parseSections(lines):
    section = None
    name = None

    for s in lines:
        s = s.strip()
        if not s.startswith("["): continue
        ix,rest = s.split(']', 1)
        if isint(ix[1:]):
            fs = map(str.strip, rest.strip().split())
            name = fs[0]
            section = Section(name)
            section.start = int(fs[2], 16)
            section.size = int(fs[4], 16)
            section.end = section.start + section.size
            yield name, section
            section = None
            name = None

def parseDwarfDump(lines):
    lasturi = None
    lastaddr = None
    lastline = None
    uri = None
    for s in lines:
        if s[0] != '0': continue

        addr,s = s.split('[', 1)
        line,s = s.split(',', 1)
        flags = s.split()[1:]

        addr = int(addr, 16)
        line = int(line)

        intext = True
        nextisuri = False
        for f in flags:
            if nextisuri:
                uri = f.strip('"')
                nextisuri = False
            if f == 'uri:': nextisuri = True
            if f == 'ET': intext = False
            else: continue

        assert uri is not None

        #print 'curr', uri,line,addr,intext
        #print 'prev', lasturi, lastline, lastaddr

        if lastaddr is not None:
            #print 'blaming', lastline, 'in', lasturi, 'for', '%d..%d' % (lastaddr, addr)
            yield (lastaddr, addr, lasturi, lastline)

        lasturi = uri
        if intext:
            lastaddr = addr
            lastline = line
        # If this was an end-of-text entry, don't count the bytes between this one and the next
        else:
            lastaddr = None

def blameLines(data, text = None):
    files = {}
    lines = set()

    for start,end,uri,line in data:
        # Ignore code from before the start of .text.
        #
        # Code that has been removed by --gc-sections will actually have all
        # its debug info left around, just with the code address set to 0.
        #
        # This is a bit messier for shared libraries where most addresses are
        # stored relative to the start of the .so file - then this only works
        # as long as functions are smaller than the size of all stuff before
        # the .text section begins.
        if text and start < text.start: continue

        file = files.setdefault(uri, File(uri))
        l = file.add(line, start, end - start)
        lines.add(l)

    return files, lines

def perc(x, total):
    return 100 * float(x) / total

def dumpCanon(files):
    res = []
    for uri in sorted(files.keys()):
        f = files[uri]
        for i,l in sorted(f.lines.items()):
            for off,len in sorted(l.places):
                res.append((off, off+len, uri, i))
    return res

def test():
    data = \
"""0x000024c0  [  52, 0] NS uri: "f1"
0x000024d5  [1127, 0] NS uri: "f2"
0x000024e8  [1098, 0] NS
0x0000253b  [1123, 0] NS
0x0000255c  [1123, 0] NS ET
0x00000bf0  [ 944, 0] NS
0x00000bf7  [ 948, 0] NS
0x00000bff  [ 948, 0] NS ET""".split('\n')
    parsedData = list(parseDwarfDump(data))
    files, lines = blameLines(parsedData)
    actual = dumpCanon(files)
    expected = [
        (0x24c0, 0x24d5, "f1", 52),
        (0xbf0, 0xbf7, "f2", 944),
        (0xbf7, 0xbff, "f2", 948),
        (0x24e8, 0x253b, "f2", 1098),
        (0x253b, 0x255c, "f2", 1123),
        (0x24d5, 0x24e8, "f2", 1127),
    ]
    assert actual == expected, repr(dumpCanon(files))+" != "+repr(expected)
    assert actual == sorted(parsedData, key = lambda l: l[2:])

test()

import os
import subprocess
import sys

binaryFile = None

if len(sys.argv) == 2:
    binaryFile = sys.argv[1]

sections = {}

if binaryFile:
    sections = dict(parseSections(os.popen("readelf -SW "+binaryFile)))
    sys.stdin = os.popen("dwarfdump -l " + binaryFile)

text = sections.get('.text')
files, lines = blameLines(parseDwarfDump(sys.stdin), text)

textBytes = text.size
totalBytes = sum(map(File.getTotal, files.values()))

N_FILES = 20
N_LINES = 20
printAllPlaces = False

#print 'TOTALS'
#print '.text size: %d bytes' % text.size
#print 'blamed bytes: %d bytes (%2.1f%%)' % (totalBytes, perc(totalBytes, text.size))
#print

print 'FILE SUMMARY (out of %d files)' % len(files)
allFiles = files.values()
allFiles.sort(key = File.getTotal, reverse = True)
for f in allFiles[:N_FILES]:
    bytes = f.total
    print '%s: %d bytes (%2.1f%%) in %d places/%d lines' % (f.uri, bytes, perc(bytes, totalBytes), f.getTotalPlaces(), len(f.lines))

print
print 'LINE SUMMARY'
for l in sorted(lines, key = lambda l: l.total, reverse = True)[:N_LINES]:
    print '%s:%d: %d bytes in %d places' % (l.uri(), l.line, l.total, len(l.places))
    if printAllPlaces:
        for offset,length in l.places:
            print '\t%x..%x' % (offset, offset + length)
