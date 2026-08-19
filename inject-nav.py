#!/usr/bin/env python3
"""Inject the shared nav + noindex meta into the generated GEMHUNT page.

gemhunt-dash.py owns that file and rewrites it every 15 min, so the nav is added
at publish time rather than in the generator. Idempotent.
"""
import sys

NAV = ('<div class="nav" style="display:flex;gap:14px;margin:0 0 18px;font-size:13px">'
       '<a href="./" style="color:var(--dim);text-decoration:none">overview</a>'
       '<a href="gemhunt.html" style="color:var(--fg);text-decoration:none;'
       'border-bottom:2px solid var(--accent);padding-bottom:3px">gemhunt board</a>'
       '<a href="ratio.html" style="color:var(--dim);text-decoration:none">ccu / visits</a>'
       '</div>')

p = sys.argv[1]
h = open(p).read()
if 'name="robots"' not in h:
    h = h.replace('<meta charset="utf-8">',
                  '<meta charset="utf-8">\n<meta name="robots" content="noindex,nofollow">', 1)
if 'class="nav"' not in h:
    anchor = '<div class="stats" id="stats"></div>'
    if anchor not in h:
        sys.exit('nav anchor not found in %s — dashboard template changed' % p)
    h = h.replace(anchor, anchor + '\n' + NAV, 1)
open(p, 'w').write(h)
print('nav+meta ok:', p)
