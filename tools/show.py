path = r'D:\projects\website\app\database.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'Jaipur' in l:
        for j in range(max(0,i-2), min(len(lines), i+6)):
            print(j+1, repr(lines[j]))
        break
