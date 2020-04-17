import re

r = re.compile('.*/.*/.*:.*')
if r.match('x/x/xxxx xx:xx') is not None:
    print('matches')
