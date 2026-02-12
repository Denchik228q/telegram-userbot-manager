#!/usr/bin/env python3

with open('manager_bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

seen_functions = {}
result_lines = []
skip_until = -1

for i, line in enumerate(lines):
    if i < skip_until:
        continue
    
    if line.startswith('async def '):
        func_name = line.split('(')[0].replace('async def ', '').strip()
        
        if func_name in seen_functions:
            for j in range(i+1, len(lines)):
                if lines[j].startswith('async def ') or lines[j].startswith('def ') or lines[j].startswith('class '):
                    skip_until = j
                    break
            else:
                skip_until = len(lines)
            continue
        else:
            seen_functions[func_name] = i
    
    result_lines.append(line)

with open('manager_bot_clean.py', 'w', encoding='utf-8') as f:
    f.writelines(result_lines)

print(f"✅ Removed {len(lines) - len(result_lines)} lines")
