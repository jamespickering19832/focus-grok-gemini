import os
import sys

temp_file_path = sys.argv[1]
target_file_path = sys.argv[2]

with open(temp_file_path, "r") as temp_f:
    content = temp_f.read()

with open(target_file_path, "w") as target_f:
    target_f.write(content)

os.remove(temp_file_path)
