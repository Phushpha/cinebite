path = 'D:/projects/website/app/database.py'
with open(path, 'rb') as f:
    data = f.read()
old = b'''      ("Jaipur", 0.85, [
          ("Raj Mandir Cinema", "Ashok Marg", ["GOLD CLASS", "AUD 2"]),
          ("PVR Malls Mall", "Vaishali Nagar", ["AUD 1", "AUD 2"]),
          ("Cinepolis World Trade Park", "Malviya Nagar", ["AUD 1", "AUD 3"]),
      ]),
  ]'''
if old not in data:
    print('MISS')
else:
    data = data.replace(old, old + b'''\n      ("Bokaro", 0.80, [
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
    with open(path, 'wb') as f:
        f.write(data)
    print('OK')