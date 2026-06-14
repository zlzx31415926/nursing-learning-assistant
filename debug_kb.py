import os, glob
kb = r'C:\Users\张林子翔\Desktop\学习助手\knowledge_base'
for f in sorted(glob.glob(os.path.join(kb, '*.md'))):
    name = os.path.basename(f)
    stem = name.replace('_六阶段学习环.md', '').replace('-六阶段学习环.md', '')
    size = os.path.getsize(f)
    print(f"Filename: {name}")
    print(f"Stem:     {stem}")
    print(f"Size:     {size}")
    print()
