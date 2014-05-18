#!/bin/bash
#vim:et:

if ! [ $# -eq 2 ]; then
    cat >&2 <<EOF
Usage: $0 SOURCE DEST

$0 compiles a C source with specific settings into an object file suitable for
consumption by sauce.py.
EOF
    exit 1
fi

exec gcc -c -o "$2" -x c "$1" -g -Wl,--gc-sections -ffunction-sections -fdata-sections
