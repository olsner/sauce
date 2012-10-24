#!/bin/bash
#vim:et:

usage() {
    cat >&2 <<EOF
Usage: test.sh <source
Compiles source from standard input to a temporary file using gcc, then runs
sauce.py on it.
EOF
    return $1
}

tempf="`mktemp`" || exit 1
./testcompile.sh - "$tempf" &&
./sauce.py "$tempf"
e=$?
rm -f "$tempf"
exit $e
