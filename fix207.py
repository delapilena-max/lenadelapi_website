# fix207.py
path = "face_cache_builder.py"
lines = open(path, encoding="utf-8").readlines()
lines[206] = lines[206].replace(
    'querySelector(\'input[type="file"]\')' ,
    "querySelector('input[type=file]')"
)
open(path, "w", encoding="utf-8").writelines(lines)
print("Fixed line 207:", lines[206].strip())
