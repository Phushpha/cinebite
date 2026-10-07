path = 'D:/projects/website/app/database.py'
with open(path, 'r', encoding='utf-8') as f:
    data = f.read()
i = data.find('"Jaipur"')
if i == -1:
    print('NO')
else:
    # look backwards to find start of this tuple line
    start = data.rfind('      ("', 0, i)
    end = data.find('  ]', i)
    if start == -1 or end == -1:
        print('PARTIAL')
    else:
        block = data[start:end+4]
        print(block)
