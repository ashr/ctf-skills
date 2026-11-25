#!/usr/bin/env python3
# Extract secretsdump cached-cred lines to hashcat -m 2100 (mscash2) format
# Usage: secretsdump.py -sam SAM -system SYSTEM -security SECURITY LOCAL | dcc2reformat
import sys, re

pat = re.compile(r'\$DCC2\$\d+#[^#]+#[0-9a-fA-F]+')
for line in sys.stdin:
    m = pat.search(line)
    if m:
        print(m.group())
