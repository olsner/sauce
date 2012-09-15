#!/usr/bin/env python
# vim:et:

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

    def __str__(self):
        return "File(%s,%d bytes in %d lines)" % (self.uri, self.total, len(self.lines))

    def __repr__(self):
        return "File(%s,%d bytes in %d lines)" % (repr(self.uri), self.total, len(self.lines))

def parseDwarfDump(lines):
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
        yield (addr, uri, line, intext)

def blameLines(data):
    files = {}
    lines = set()

    lasturi = None
    lastaddr = None
    lastline = None
    file = None
    for addr,uri,line,intext in data:
        #print 'curr', uri,line,addr,intext
        #print 'prev', lasturi, lastline, lastaddr

        if lastaddr is not None:
            #print 'blaming', lastline, 'in', file.uri, 'for', '%d..%d' % (lastaddr, addr)
            l = file.add(lastline, lastaddr, addr - lastaddr)
            lines.add(l)
        if uri != lasturi:
            file = files.setdefault(uri, File(uri))
            lasturi = uri

        if intext:
            lastaddr = addr
            lastline = line
        # If this was an end-of-text entry, don't count the bytes between this one and the next
        else:
            lastaddr = None

    return files, lines

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
    files, lines = blameLines(parseDwarfDump(data))
    assert dumpCanon(files) == [
        (0x24c0, 0x24d5, "f1", 52),
        (0xbf0, 0xbf7, "f2", 944),
        (0xbf7, 0xbff, "f2", 948),
        (0x24e8, 0x253b, "f2", 1098),
        (0x253b, 0x255c, "f2", 1123),
        (0x24d5, 0x24e8, "f2", 1127),
    ]

test()

import os
import subprocess
import sys

files, lines = blameLines(parseDwarfDump(sys.stdin))

# TODO Examine the binary, see how big the .text section is (used to find code
# that has no lines associated).
# textBytes = ???
totalBytes = sum(map(File.getTotal, files.values()))

N_FILES = 20
N_LINES = 20
printAllPlaces = False

print 'FILE SUMMARY (out of %d files)' % len(files)
allFiles = files.values()
allFiles.sort(key = File.getTotal, reverse = True)
for f in allFiles[:N_FILES]:
    bytes = f.total
    print '%s: %d bytes (%2.1f%%)' % (f.uri, bytes, 100 * float(bytes) / totalBytes)

print
print 'LINE SUMMARY'
for l in sorted(lines, key = lambda l: l.total, reverse = True)[:N_LINES]:
    print '%s:%d: %d bytes' % (l.uri(), l.line, l.total)
    if printAllPlaces:
        for offset,length in l.places:
            print '\t%x..%x' % (offset, offset + length)
