import re
import subprocess

def replace_string_in_file(file_path, old_string, new_string):
    # Read in the file
    with open(file_path, 'r') as file:
        filedata = file.read()

    # Replace the target string
    new_filedata = re.sub(old_string, new_string, filedata)

    # Write the file out again
    with open(file_path, 'w') as file:
        file.write(new_filedata)
        
def command_execute(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    print(result)
