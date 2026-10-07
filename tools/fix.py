path = 'D:/projects/website/app/database.py'
with open(path, 'rb') as f:
    d = f.read()
# get actual byte pattern
idx = d.find(b'"Jaipur"')
if idx == -1:
    raise SystemExit('no jaipur')
# walk backwards to find "  ])," that closes the list
# easier: find the exact tail
pass
# just cut from Jaipur line start to the final ] before the closing of CITIES list?
# see: in our file, after Jaipur block is ), then space+]
# look for b')\n  ]' near there
tail = d.find(b')\n  ]', idx)
if tail == -1:
    tail = d.find(b')\r\n  ]', idx)
if tail == -1:
    raise SystemExit('tail')
start = d.rfind(b'      ("Jaipur"', 0, idx)
if start == -1:
    raise SystemExit('start')
old = d[start:tail+4]
print('OLD_LEN', len(old))
# append new
new = old + b'''\n      ("Bokaro", 0.80, [
          ("INOX Bokaro City Centre", "Sector 4", ["IMAX", "AUD 2"]),
          ("Cinepolis Bokaro Mall", "Sector 5", ["AUD 1", "AUD 2"]),
          ("PVR Bokaro Heights", "City Centre", ["AUD 1", "AUD 3"]),
      ]),
      ("Ranchi", 0.90, [
          ("PVR Nucleus Mall", "Lalpur", ["IMAX", "AUD 2"]),
          ("INOX JD Hi Street Mall", "Tharpakhna", ["AUD 1", "AUD 2"]),
          ("Cinepolis Spring City", "Harmu", ["AUD 1", "AUD 2"]),
      ]),
      ("Dhanbad", 0.80, [
          ("INOX Dhanbad Mall", "Bank More", ["AUD 1", "AUD 2"]),
          ("PVR Ozone Galleria", "Saraidhela", ["AUD 1", "AUD 2"]),
          ("Cinepolis Ispat Nagar", "Ispat Nagar", ["AUD 1", "AUD 3"]),
      ]),
'''
d2 = d.replace(old, new)
with open(path, 'wb') as f:
    f.write(d2)
print('OK')