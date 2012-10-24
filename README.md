What's sauce?
-------------

Sauce is a tool to figure out where each byte of machine code in a binary (or
shared library) came from. It works with ELF files that have dwarf debug info,
using the line number information to figure out which code to blame for the
bytes.

Sauce dependencies:

- Python
- readelf: should be included in binutils
- dwarfdump: you may need to install this one manually, but it appears to have
  packages for popular Linuxes already.

Other than these external dependencies the sauce.py script is free-standing,
and doesn't need any installation. The repo contains some test scripts that are
not required for running sauce.py.

How do I use it?
----------------

The simplest mode of operation is to, well, run sauce.py on your binary:

	# Imagine an Android project with some JNI code:
	./sauce.py obj/local/armeabi/libfoo.so

This will produce a summary of the worst offending individual lines and files
(based on the sum of bytes blamed on a source line in that file).

Note that code from inlined functions will be blamed on the file/lines where
the inlined function was defined, and the code calling the function will
appear completely innocent. Sometimes this is what you want, e.g. to find a
force-inlined function that takes space for each use. Other times this is not
what you want, e.g. for an often-inlined getter where the inlined code might be
about the same size (or smaller!) than a non-inlined call would be.

Caveats and possible bugs
-------------------------

- The test suite is too small :)
- Inlined functions may be counted in surprising ways (see above)
- The --gc-sections linker flag has caused problems before. The problem here is
  that even though the code is thrown away by the linker, the debug info is
  *not* thrown away. The tool tries to filter out line number info that appears
  to come from garbage collected functions, but this is not completely reliable.
- Untested using Gold's ICF (identical code folding) feature.
  There's an interpretation question here, somewhat similar to inlined
  functions - whose fault is it that the bytes are in the binary? Are any of
  the identical functions more or less to blame than the others?

Future ideas
------------

- Generate a summary of functions (and data!) by size. The major reason it
  doesn't do this already is that it requires completely different data from
  the binary, unrelated to the line number info.
- Add some options to print more than the very sparse summary output
- Build in a web server, allow interactive navigation around the data
- As an alternative to the web server, just generate a big HTML file using
  JavaScript to make it nice and interactive.
- Add machine-readable "dump" output, make it possible to diff two dumps and
  e.g. show which code grew, what got smaller, etc.

License
-------

Sauce is distributed under an MIT license. See the COPYING file in the root of
the source tree.
