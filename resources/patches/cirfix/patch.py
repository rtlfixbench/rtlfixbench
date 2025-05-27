import os
import shutil
import site

script_directory = os.path.dirname(os.path.abspath(__file__))
source_directory = os.path.join(script_directory, 'pyverilog')

# Detect the default site-packages directory
site_packages_dirs = site.getsitepackages()

# Filter out directories that don't exist or aren't relevant
site_packages_dir = None
for dir_path in site_packages_dirs:
    if os.path.exists(dir_path):
        site_packages_dir = dir_path
        break

if not site_packages_dir:
    raise FileNotFoundError("Could not find the default site-packages directory.")

print(f"Detected site-packages directory: {site_packages_dir}")

# Define the relative paths for the target files inside pyverilog
target_files = {
    'codegen.py': os.path.join(site_packages_dir, 'pyverilog', 'ast_code_generator', 'codegen.py'),
    'ast.py': os.path.join(site_packages_dir, 'pyverilog', 'vparser', 'ast.py'),
    'parser.py': os.path.join(site_packages_dir, 'pyverilog', 'vparser', 'parser.py'),
    'ast_classes.txt': os.path.join(site_packages_dir, 'pyverilog', 'vparser', 'ast_classes.txt')
}

for file_name, target_path in target_files.items():
    source_file = os.path.join(source_directory, file_name)
    
    if not os.path.isfile(source_file):
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    print(f"Copying {source_file} -> {target_path}")
    shutil.copy2(source_file, target_path)

    if file_name == "parser.py":
        print(f"Updating path in {target_path}")
        with open(target_path, 'r') as file:
            file_content = file.read()
        
        # Replace the hardcoded path with the detected site-packages directory
        file_content = file_content.replace(
            "/path/to/site-packages/", 
            site_packages_dir + "/"
        )
        
        # Write the updated content back to the file
        with open(target_path, 'w') as file:
            file.write(file_content)
