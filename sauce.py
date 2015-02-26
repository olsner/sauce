#!/usr/bin/env python
#
# Copyright (c) 2012-2014 Simon Brenner
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

import cPickle
import operator
import os
import posixpath
import re
import subprocess
import sys

class Section(object):
    def __init__(self, name):
        self.name = name
        self.start = None
        self.end = None
        self.size = None

    def __repr__(self):
        return "%s: %x..%x" % (self.name, self.start, self.end)

def merge((s1, l1), (s2, l2)):
    assert s1 <= s2
    e1 = s1 + l1
    e2 = s2 + l2

    if s2 <= e1:
        s = min(s1, s2)
        e = max(e1, e2)
        return (s, e - s)

    return None

def mergeRanges(ps):
    ps = sorted(ps)
    prev = None
    for p in ps:
        if prev is None:
            prev = p
            continue

        merged = merge(prev, p)
        if merged:
            prev = merged
        else:
            yield prev
            prev = p
    if prev:
        yield prev

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

    def fix(self):
        self.places = list(mergeRanges(self.places))

    def getAveragePerPlace(self):
        return self.total / max(1, len(self.places))

    def dump(self):
        print self.line, ":", self.total, "bytes:",
        for offset,length in self.places:
            print "%x..%x" % (offset, offset + length),
        print

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

    def getAveragePerPlace(self):
        return self.total / max(1, self.getTotalPlaces())

    def __str__(self):
        return "File(%s,%d bytes in %d lines)" % (self.uri, self.total, len(self.lines))

    def __repr__(self):
        return "File(%s,%d bytes in %d lines)" % (repr(self.uri), self.total, len(self.lines))

    def dump(self):
        print "FILE DETAIL", repr(self.uri)
        print self.total, "total bytes in", len(self.lines), "lines:"
        for num, line in sorted(self.lines.iteritems()):
            line.dump()

    def makeDisassembly(self, disasm, outfolder):
        for _,l in sorted(self.lines.items()):
            #print f,l
            print '%s:%d: (%d places)' % (self.uri, l.line, len(l.places))
            for offset,length in l.places:
                for x in range(offset, offset + length):
                    if x in disasm: print disasm[x]

class Node(object):
    def __init__(self):
        self.children = {}
        self.total = None

    def getTotal(self):
        if self.total is None:
            self.total = reduce(operator.add, (n.getTotal() for n in self))
        return self.total

    # Perhaps we could use a catch-all to forward "everything else" to self.children?
    def __getitem__(self, *args):
        return self.children.__getitem__(*args)

    def __setitem__(self, *args):
        return self.children.__setitem__(*args)

    def __iter__(self):
        return self.children.itervalues()

    def iteritems(self):
        return self.children.iteritems()

    def setdefault(self, key, default):
        return self.children.setdefault(key, default)

    def __repr__(self):
        return repr(self.children)

    def __str__(self):
        return str(self.children)

def treeify(files):
    dest = Node()
    for uri,f in files.iteritems():
        # Assumes posix path. Add a conversion step somewhere if you want to
        # run on Windows.
        path = uri.lstrip('/')
        node = dest
        components = path.split('/')
        for p in components[:-1]:
            node = node.setdefault(p, Node())
        node[components[-1]] = f
    return dest

# TODO Would be nice to squash together subdirectory structures that don't have
# any files, and recognize if there's a common prefix of all files.
def dump_tree_du(h, tree, path = '/'):
    if isinstance(tree, Node):
        for k,v in tree.iteritems():
            dump_tree_du(h, v, os.path.join(path, k))
    print >>h, tree.getTotal(), path

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

def getTextSection(sections):
    texts = []
    for k in sections:
        if k.startswith(".text"): texts.append(sections[k])
    start,end = None,None
    # Size minus any holes in the address space.
    totalSize = 0
    for a in texts:
        if start is None or a.start < start: start = a.start
        if end is None or a.end > end: end = a.end
        totalSize += a.size
    vText = Section(".text")
    vText.start = start
    vText.end = end
    vText.size = end - start
    vText.totalSize = totalSize
    return vText

def parseDisasm(lines):
    codeline = re.compile('^ *([0-9a-f]+):\s*(.*)$')
    # some intereseting formats:
    # "  100000:       02 b0 ad 1b 02 00       add    0x21bad(%rax),%dh"
    # - disasm for a short address (space-padded, starts at column 0)
    # "ffffffffc0100290:       89 f0                   mov    %esi,%eax"
    # - disasm for long address (starts in column 0)
    # some uninteresting formats:
    # 0000000000100172 <start32.fill_pd>:
    res = {}
    for s in lines:
        s = s.rstrip()
        m = codeline.match(s)
        if m: res[int(m.group(1), 16)] = s
    return res

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

        uri = os.path.normpath(uri)
        file = files.setdefault(uri, File(uri))
        l = file.add(line, start, end - start)
        lines.add(l)

    map(Line.fix, lines)
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

sections = {}
disasm = {}
binaryFile = None
files = None

# TODO There's no excuse anymore, add an argument parser.
if len(sys.argv) == 2:
    binaryFile = sys.argv[1]

# Should be a command-line option
dumpPickle = None
# Another command-line option: display code size per file and directory like
# du. Run through 'sort -n' to get an idea of components that cause bloat.
dumpDuData = False
# summary: the normal output mode, prints a summary of the 20 most bloated
# files and lines.
summary = not dumpDuData
# Display every byte range for every displayed file/line pair
printAllPlaces = False
# Display disassembly for top places
topPlaceDisasm = True
# Display disassembly for all lines in all files
fullDisassembly = False

# TODO Don't print the messages unless "verbose"
if binaryFile and binaryFile.endswith(".pickle"):
    print "Loading parsed data from pickle..."
    sections,files,lines = cPickle.load(open(binaryFile, "rb"))
    print "done."
elif binaryFile:
    sections = dict(parseSections(os.popen("readelf -SW "+binaryFile)))
    sys.stdin = os.popen("dwarfdump -l " + binaryFile)
    disasm = parseDisasm(os.popen("objdump -Cd "+binaryFile))

text = getTextSection(sections)
textBytes = text.totalSize

if files is None:
    print "Parsing dwarfdump..."
    files, lines = blameLines(parseDwarfDump(sys.stdin), text)
    if dumpPickle:
        print "Dumping parsed data to %s..." % dumpPickle
        cPickle.dump((sections,files,lines), open(dumpPickle, "wb"))
    print "done."

totalBytes = sum(map(File.getTotal, files.values()))

N_FILES = 20
N_LINES = 20

if summary:
    print 'TOTALS'
    if textBytes:
        print '.text size: %d bytes' % textBytes
        print 'blamed bytes: %d bytes (%2.1f%%)' % (totalBytes, perc(totalBytes, textBytes))
    else:
        print '.text size unknown.'
        print 'blamed %d bytes' % totalBytes

# Fudge constant to attempt to get rid of "trivial" inlines. The effect is to
# only count files/lines where the average number of bytes per place (a "place"
# is any contiguous range of bytes) is above a number vaguely related to the
# cost of a function call. The idea is that inlined code blocks smaller than
# this number is from "trivial" functions that would not be smaller if
# uninlined.
PER_PLACE_MIN = 0

if summary and N_FILES:
    print
    print 'FILE SUMMARY (out of %d files)' % len(files)
    allFiles = files.values()
    allFiles = filter(lambda f: f.getAveragePerPlace() > PER_PLACE_MIN, allFiles)
    allFiles.sort(key = File.getTotal, reverse = True)
    for f in allFiles[:N_FILES]:
        bytes = f.total
        print '%s: %d bytes (%2.1f%%) in %d places/%d lines, %2.1f bytes/place' % (f.uri, bytes, perc(bytes, totalBytes), f.getTotalPlaces(), len(f.lines), f.getAveragePerPlace())

if summary and N_LINES:
    print
    print 'LINE SUMMARY'
    lines = filter(lambda l: l.getAveragePerPlace() > PER_PLACE_MIN, lines)
    for l in sorted(lines, key = lambda l: l.total, reverse = True)[:N_LINES]:
        print '%s:%d: %d bytes in %d places, %2.1f bytes/place' % (l.uri(), l.line, l.total, len(l.places), float(l.total) / len(l.places))
        if topPlaceDisasm:
            for offset,length in l.places:
                for x in range(offset, offset + length):
                    if x in disasm: print disasm[x]
        if printAllPlaces:
            for offset,length in l.places:
                print '\t%x..%x' % (offset, offset + length)

if fullDisassembly:
    print
    print 'ANNOTATED DISASSEMBLY'
    for f in allFiles:
        f.makeDisassembly(disasm, "usage")

if dumpDuData:
    dump_tree_du(sys.stdout, treeify(files))
