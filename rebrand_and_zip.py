import os
import zipfile
import shutil
import re

ZIP_PATH = r"c:\Users\gegas\Documents\antigravity\excited-davinci\BlenderAddon\v16_hunyuan2-stableprojectorz.zip"
TEMP_DIR = r"c:\Users\gegas\Documents\antigravity\excited-davinci\backend_temp"
OUT_ZIP_PATH = r"c:\Users\gegas\Documents\antigravity\excited-davinci\Geguchh_v16_hunyuan2.zip"

def extract_zip(zip_path, extract_to):
    print(f"Extracting {zip_path} to {extract_to}...")
    if os.path.exists(extract_to):
        shutil.rmtree(extract_to)
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print("Extraction complete.")

def rebrand_files(root_dir):
    print("Rebranding file contents...")
    text_extensions = {'.py', '.bat', '.sh', '.json', '.txt', '.html', '.md', '.ini', '.cfg'}
    
    replacements = [
        (re.compile(re.escape("StableProjectorz"), re.IGNORECASE), "Geguchh"),
        (re.compile(re.escape("stable-projectorz"), re.IGNORECASE), "geguchh"),
        (re.compile(re.escape("stable projectorz"), re.IGNORECASE), "geguchh"),
        (re.compile(re.escape("stable_projectorz"), re.IGNORECASE), "geguchh"),
        (re.compile(re.escape("Hunyuan3D-2-stable-projectorz"), re.IGNORECASE), "Geguchh-Hunyuan2"),
        (re.compile(re.escape("spz-internal.bat")), "geguchh-internal.bat"),
        (re.compile(re.escape("spz_internal")), "geguchh_internal"),
        (re.compile(re.escape("api_spz")), "api_geguchh"),
        (re.compile(re.escape("run-projectorz_(faster)")), "run-geguchh_(faster)"),
        (re.compile(re.escape("_spz")), "_geguchh"),
        (re.compile(r"\bspz\b", re.IGNORECASE), "geguchh"),
        (re.compile(r"\bprojectorz\b", re.IGNORECASE), "geguchh"),
    ]

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip git directory
        if '.git' in dirpath.split(os.sep):
            continue
            
        for filename in filenames:
            # Skip get-pip.py and other third-party package files to avoid corruption
            if filename == "get-pip.py" or filename.endswith(".pyd") or filename.endswith(".dll"):
                continue
                
            ext = os.path.splitext(filename)[1].lower()
            if ext in text_extensions:
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    original_content = content
                    for pattern, repl in replacements:
                        content = pattern.sub(repl, content)
                    
                    if content != original_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"  Rebranded contents of: {os.path.relpath(file_path, root_dir)}")
                except Exception as e:
                    print(f"  Failed to process {file_path}: {e}")

def rename_files_and_folders(root_dir):
    print("Renaming directories and files...")
    
    # 1. Rename directories
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        for dirname in dirnames:
            new_dirname = dirname
            if "projectorz" in dirname.lower():
                new_dirname = dirname.lower().replace("projectorz", "geguchh")
            elif "spz" in dirname.lower():
                new_dirname = dirname.lower().replace("spz", "geguchh")
                
            if new_dirname != dirname:
                old_path = os.path.join(dirpath, dirname)
                new_path = os.path.join(dirpath, new_dirname)
                if os.path.exists(new_path):
                    shutil.rmtree(new_path, ignore_errors=True)
                shutil.move(old_path, new_path)
                print(f"  Renamed directory: {os.path.relpath(old_path, root_dir)} -> {new_dirname}")

    # 2. Rename files
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        for filename in filenames:
            new_filename = filename
            if "stableprojectorz" in filename.lower():
                new_filename = filename.lower().replace("stableprojectorz", "geguchh")
            elif "spz-internal" in filename.lower():
                new_filename = filename.lower().replace("spz-internal", "geguchh-internal")
            elif "spz" in filename.lower():
                new_filename = filename.lower().replace("spz", "geguchh")
                
            if new_filename != filename:
                old_path = os.path.join(dirpath, filename)
                new_path = os.path.join(dirpath, new_filename)
                if os.path.exists(new_path):
                    os.remove(new_path)
                os.rename(old_path, new_path)
                print(f"  Renamed file: {os.path.relpath(old_path, root_dir)} -> {new_filename}")

def compress_zip(source_dir, output_zip):
    print(f"Compressing {source_dir} to {output_zip}...")
    if os.path.exists(output_zip):
        os.remove(output_zip)
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        for dirpath, dirnames, filenames in os.walk(source_dir):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                arcname = os.path.relpath(file_path, source_dir)
                zip_ref.write(file_path, arcname)
    print("Compression complete.")

if __name__ == "__main__":
    if not os.path.exists(ZIP_PATH):
        print(f"Error: Original zip not found at {ZIP_PATH}")
    else:
        extract_zip(ZIP_PATH, TEMP_DIR)
        rebrand_files(TEMP_DIR)
        rename_files_and_folders(TEMP_DIR)
        rebrand_files(TEMP_DIR)
        compress_zip(TEMP_DIR, OUT_ZIP_PATH)
        print("Cleaning up temp folder...")
        shutil.rmtree(TEMP_DIR)
        print("All processes successfully completed!")
