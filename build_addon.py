import os
import zipfile

ADDON_DIR = r"c:\Users\gegas\Documents\antigravity\excited-davinci\hunyuan3d_generator"
OUT_ZIP_PATH = r"c:\Users\gegas\Documents\antigravity\excited-davinci\hunyuan3d_generator.zip"

def build_addon():
    print(f"Building lightweight Blender Addon zip from {ADDON_DIR}...")
    if os.path.exists(OUT_ZIP_PATH):
        os.remove(OUT_ZIP_PATH)
        
    with zipfile.ZipFile(OUT_ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        for dirpath, dirnames, filenames in os.walk(ADDON_DIR):
            # Exclude any extracted backend to keep it lightweight
            parts = os.path.relpath(dirpath, ADDON_DIR).split(os.sep)
            if 'backend_extracted' in parts:
                continue
                
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                # We want the folder structure in the zip to start with hunyuan3d_generator/
                arcname = os.path.join("hunyuan3d_generator", os.path.relpath(file_path, ADDON_DIR))
                zip_ref.write(file_path, arcname)
                print(f"  Added to zip: {arcname}")
                
    print(f"Successfully created Blender Addon zip at: {OUT_ZIP_PATH}")
    print(f"Size: {os.path.getsize(OUT_ZIP_PATH)} bytes")

if __name__ == "__main__":
    build_addon()
