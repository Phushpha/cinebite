path = r'D:\projects\website\app\database.py'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    s = f.read()
i = s.find('Jaipur')
print(i)