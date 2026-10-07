path = r'D:\projects\website\app\database.py'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    s = f.read()

marker = '''      ("Jaipur", 0.85, [
          ("Raj Mandir Cinema", "Ashok Marg", ["GOLD CLASS", "AUD 2"]),
          ("PVR Malls Mall", "Vaishali Nagar", ["AUD 1", "AUD 2"]),
          ("Cinepolis World Trade Park", "Malviya Nagar", ["AUD 1", "AUD 3"]),
      ]),
  ]'''

if marker not in s:
    # try exact spacing
    # maybe spaces/tabs differ
    print('MISS')
else:
    s2 = s.replace(marker, marker[:-5] + '''\n      ("Bokaro", 0.80, [
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
  ]''')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(s2)
    print('OK')