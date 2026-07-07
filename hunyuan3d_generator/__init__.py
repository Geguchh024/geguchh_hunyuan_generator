bl_info = {
    "name": "Geguchh Hunyuan2 3D Generator",
    "author": "Geguchh",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Geguchh Hunyuan2",
    "description": "Generate 3D models and texture meshes using local Hunyuan3D-2 backend.",
    "category": "3D View",
}

import bpy
import os
import sys
import json
import urllib.request
import urllib.error
import base64
import tempfile
import threading
import subprocess
import time
import socket
import traceback

# Global state dictionary for communication between threads and Blender's main thread
class GlobalAddonState:
    # Installation & Setup state
    is_downloading = False
    download_percent = 0.0
    download_bytes = 0
    download_total = 0
    download_error = ""
    
    is_setting_up = False
    setup_percent = 0
    setup_status = "Not started"
    setup_log = []
    
    # Cached statuses to avoid disk lag in Blender draw loop
    status_initialized = False
    is_installed = False
    weights_cached = False
    
    # Server state
    server_process = None
    server_status = "STOPPED" # STOPPED, STARTING, RUNNING, ERROR
    server_error = ""
    
    # Generation state
    is_generating = False
    generation_progress = 0
    generation_status = ""
    generation_error = ""
    generation_success_file = ""
    target_mesh_name = ""
    apply_to_selected = False

state = GlobalAddonState()

# Helper: check if a port is open
def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.05) # 50ms is plenty for localhost connections
        try:
            s.connect(('127.0.0.1', port))
            return True
        except Exception:
            return False

# Helper: check setup state for a given path
def check_backend_installed(backend_path):
    if not backend_path or not os.path.exists(backend_path):
        return False
    venv_py = os.path.join(backend_path, "code", "venv", "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        venv_py_root = os.path.join(backend_path, "venv", "Scripts", "python.exe")
        if not os.path.exists(venv_py_root):
            return False
            
    init_done = os.path.join(backend_path, "code", "hunyuan_init_done.txt")
    if not os.path.exists(init_done):
        server_py = os.path.join(backend_path, "code", "api_server.py")
        if not os.path.exists(server_py):
            return False
            
    return True

# Helper: check if model weights are cached in Hugging Face directory
def check_weights_installed(model_path):
    model_folder = "models--" + model_path.replace("/", "--")
    
    env_cache = os.environ.get("HF_HUB_CACHE")
    if env_cache and os.path.exists(os.path.join(env_cache, model_folder)):
        return True
        
    env_home = os.environ.get("HF_HOME")
    if env_home and os.path.exists(os.path.join(env_home, "hub", model_folder)):
        return True
        
    user_home = os.path.expanduser("~")
    default_path = os.path.join(user_home, ".cache", "huggingface", "hub", model_folder)
    if os.path.exists(default_path):
        return True
        
    default_hub = os.path.join(user_home, ".cache", "huggingface", "hub")
    if os.path.exists(default_hub):
        try:
            for item in os.listdir(default_hub):
                if "hunyuan3d-2" in item.lower() or "hunyuan3d" in item.lower():
                    return True
        except Exception:
            pass
            
    return False

# Function to update status cache safely (runs once on path edit / startup)
def update_status_cache(self=None, context=None):
    try:
        if context and hasattr(context, "scene") and hasattr(context.scene, "geguchh_props"):
            props = context.scene.geguchh_props
        elif bpy.context and hasattr(bpy.context, "scene") and hasattr(bpy.context.scene, "geguchh_props"):
            props = bpy.context.scene.geguchh_props
        else:
            return
            
        backend_dir = os.path.normpath(props.backend_path)
        state.is_installed = check_backend_installed(backend_dir)
        state.weights_cached = check_weights_installed(props.model_path)
        
        # Check if port is open to sync running status (e.g. if started outside or reloaded)
        if is_port_open(props.api_port):
            state.server_status = "RUNNING"
        else:
            if state.server_status == "RUNNING":
                state.server_status = "STOPPED"
                
        state.status_initialized = True
    except Exception as e:
        print(f"Error updating status cache: {e}")

# Helper: download function run in background thread
def download_backend_thread(url, dest_path):
    state.is_downloading = True
    state.download_percent = 0.0
    state.download_bytes = 0
    state.download_total = 0
    state.download_error = ""
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            meta = response.info()
            content_length = meta.get("Content-Length")
            if content_length:
                state.download_total = int(content_length)
            
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            chunk_size = 1024 * 1024
            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    state.download_bytes += len(chunk)
                    if state.download_total > 0:
                        state.download_percent = (state.download_bytes / state.download_total) * 100.0
                    else:
                        state.download_percent = -1.0
            
            if state.download_total > 0 and state.download_bytes < state.download_total:
                raise IOError(f"Connection closed early. Received {state.download_bytes} of {state.download_total} bytes.")
                        
        state.download_percent = 100.0
    except Exception as e:
        state.download_error = str(e)
    finally:
        state.is_downloading = False

# Helper: extract & setup run in background thread
def setup_backend_thread(zip_path, backend_path):
    state.is_setting_up = True
    state.setup_status = "Extracting files..."
    state.setup_log = []
    
    def log(msg):
        state.setup_log.append(msg)
        print(f"[Setup] {msg}")
        
    try:
        if os.path.exists(backend_path):
            state.setup_status = "Cleaning old directory..."
            import shutil
            try:
                shutil.rmtree(backend_path)
            except Exception as clean_err:
                log(f"Warning during folder cleanup: {clean_err}")
                log("Proceeding with overwrite extraction...")
            
        os.makedirs(backend_path, exist_ok=True)
        
        # 1. Unzip
        import zipfile
        log(f"Extracting zip to {backend_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(backend_path)
            
        log("Extraction complete. Setting up virtual environment...")
        
        check_path = os.path.join(backend_path, "tools", "environment.bat")
        if not os.path.exists(check_path):
            nested_folder = ""
            for item in os.listdir(backend_path):
                nested_dir = os.path.join(backend_path, item)
                if os.path.isdir(nested_dir) and os.path.exists(os.path.join(nested_dir, "tools", "environment.bat")):
                    nested_folder = item
                    break
            
            if nested_folder:
                log(f"Detected nested zip structure in folder '{nested_folder}'. Moving contents to backend root...")
                nested_root = os.path.join(backend_path, nested_folder)
                for item in os.listdir(nested_root):
                    shutil.move(os.path.join(nested_root, item), os.path.join(backend_path, item))
                os.rmdir(nested_root)
                
        # 2. Run Setup Commands via environment.bat
        log("Starting package setup script inside portable Python environment...")
        state.setup_status = "Installing packages (pip, PyTorch, packages)..."
        
        tools_dir = os.path.join(backend_path, "tools")
        setup_bat = os.path.join(tools_dir, "run_installer.bat")
        
        with open(setup_bat, "w") as f:
            f.write("@echo off\n")
            f.write("call environment.bat\n")
            f.write("cd /d ..\\code\n")
            f.write("%PYTHON% -m pip install --upgrade pip\n")
            f.write("%PYTHON% install.py\n")
            f.write("if %ERRORLEVEL% == 0 (\n")
            f.write("    echo initComplete > hunyuan_init_done.txt\n")
            f.write(")\n")
            
        # Run process
        process = subprocess.Popen(
            [setup_bat],
            cwd=tools_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            text=True
        )
        
        # Capture logs in real time
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                log(line.strip())
                
        process.communicate()
        if process.returncode != 0:
            raise Exception(f"Setup process failed with return code {process.returncode}")
            
        if os.path.exists(setup_bat):
            os.remove(setup_bat)
            
        if check_backend_installed(backend_path):
            state.setup_status = "Setup completed successfully!"
            log("Backend successfully configured!")
        else:
            raise Exception("Setup completed but verification check failed.")
            
    except Exception as e:
        state.setup_status = "Setup Failed!"
        log(f"ERROR: {str(e)}")
        for tb_line in traceback.format_exc().splitlines():
            log(tb_line)
    finally:
        state.is_setting_up = False

# Helper: generation function run in background thread
def generate_model_thread(api_url, payload, apply_to_selected, target_mesh_name):
    state.is_generating = True
    state.generation_progress = 10
    state.generation_status = "Sending request to backend server..."
    state.generation_error = ""
    state.generation_success_file = ""
    state.apply_to_selected = apply_to_selected
    state.target_mesh_name = target_mesh_name
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{api_url}/generate",
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        state.generation_progress = 30
        state.generation_status = "Processing generation on GPU (This can take 1-2 minutes)..."
        
        with urllib.request.urlopen(req, timeout=300) as response:
            glb_data = response.read()
            
        state.generation_progress = 80
        state.generation_status = "Saving generated model..."
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".glb")
        temp_file.write(glb_data)
        temp_file.close()
        
        state.generation_success_file = temp_file.name
        state.generation_progress = 100
        state.generation_status = "Generation complete! Importing..."
    except Exception as e:
        state.generation_error = str(e)
        state.generation_progress = 0
        state.generation_status = "Failed!"
    finally:
        state.is_generating = False

# =========================================================================
# Properties
# =========================================================================
class GeguchhAddonProperties(bpy.types.PropertyGroup):
    # Setup Paths (Runs cache update callback on path change)
    backend_path: bpy.props.StringProperty(
        name="Backend Folder",
        description="Path to the folder where the backend files exist (or will be extracted to)",
        default="C:\\v16_hunyuan2-stableprojectorz",
        subtype='DIR_PATH',
        update=update_status_cache
    )
    download_url: bpy.props.StringProperty(
        name="Download URL",
        description="GitHub Release URL or direct download URL for Geguchh_v16_hunyuan2.zip",
        default="https://github.com/Geguchh024/geguchh_hunyuan_generator/releases/download/v1.0.0/Geguchh_v16_hunyuan2.zip"
    )
    
    # Server configuration properties
    api_port: bpy.props.IntProperty(
        name="Server Port",
        description="Port for the FastAPI local backend server",
        default=8081,
        min=1024,
        max=65535
    )
    model_path: bpy.props.EnumProperty(
        name="Model",
        description="Hunyuan3D Model size to load",
        items=[
            ('tencent/Hunyuan3D-2mini', "Hunyuan3D-2 Mini (Recommended)", "Fast generation & lower VRAM usage"),
            ('tencent/Hunyuan3D-2', "Hunyuan3D-2 Full (Quality)", "Higher quality but slower & high VRAM usage")
        ],
        default='tencent/Hunyuan3D-2mini',
        update=update_status_cache
    )
    enable_tex: bpy.props.BoolProperty(
        name="Load Texturing Pipeline",
        description="Load the paint/texture model pipeline. Disabling saves VRAM.",
        default=True
    )
    device: bpy.props.EnumProperty(
        name="Device",
        description="Hardware acceleration device",
        items=[
            ('cuda', "GPU (CUDA)", "Use Nvidia GPU acceleration"),
            ('cpu', "CPU (Slow)", "Use CPU (not recommended)")
        ],
        default='cuda'
    )
    
    # Generation parameters
    prompt: bpy.props.StringProperty(
        name="Text Prompt",
        description="Describe the 3D model you want to generate",
        default=""
    )
    image_path: bpy.props.StringProperty(
        name="Image Path",
        description="Choose a reference image for Image-to-3D generation",
        subtype='FILE_PATH'
    )
    octree_resolution: bpy.props.IntProperty(
        name="Octree Resolution",
        description="Resolution of the generated 3D structure",
        default=256,
        min=128,
        max=512
    )
    num_inference_steps: bpy.props.IntProperty(
        name="Inference Steps",
        description="Number of diffusion inference steps",
        default=20,
        min=10,
        max=50
    )
    guidance_scale: bpy.props.FloatProperty(
        name="Guidance Scale",
        description="Classifier-free guidance scale",
        default=5.5,
        min=1.0,
        max=10.0
    )
    texture: bpy.props.BoolProperty(
        name="Generate Texture",
        description="Bake texture maps onto the 3D model",
        default=True
    )

# =========================================================================
# Operators
# =========================================================================

# Operator: Download and Configure Backend
class GEGUCHH_OT_ConfigureBackend(bpy.types.Operator):
    bl_idname = "geguchh.configure_backend"
    bl_label = "Configure & Install Backend"
    bl_description = "Download the rebranded zip from GitHub, extract, and configure Python virtual env with PyTorch"
    
    _timer = None
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            if state.is_downloading:
                context.area.tag_redraw()
                return {'PASS_THROUGH'}
                
            if not state.is_downloading and hasattr(self, 'download_active') and self.download_active:
                self.download_active = False
                if state.download_error:
                    self.report({'ERROR'}, f"Download failed: {state.download_error}")
                    self.cleanup_timer(context)
                    return {'FINISHED'}
                else:
                    props = context.scene.geguchh_props
                    backend_dir = os.path.normpath(props.backend_path)
                    zip_path = os.path.join(backend_dir, "Geguchh_v16_hunyuan2.zip")
                    self.setup_thread = threading.Thread(
                        target=setup_backend_thread, 
                        args=(zip_path, backend_dir)
                    )
                    self.setup_thread.start()
                    self.setup_active = True
                    return {'PASS_THROUGH'}
            
            if hasattr(self, 'setup_active') and self.setup_active:
                if state.is_setting_up:
                    context.area.tag_redraw()
                    return {'PASS_THROUGH'}
                else:
                    self.setup_active = False
                    # Update status indicators
                    update_status_cache(context=context)
                    
                    if "Failed" in state.setup_status:
                        self.report({'ERROR'}, f"Setup failed. Check log details.")
                    else:
                        self.report({'INFO'}, "Backend installed and configured successfully!")
                        props = context.scene.geguchh_props
                        backend_dir = os.path.normpath(props.backend_path)
                        zip_path = os.path.join(backend_dir, "Geguchh_v16_hunyuan2.zip")
                        if os.path.exists(zip_path):
                            try:
                                os.remove(zip_path)
                            except Exception:
                                pass
                    self.cleanup_timer(context)
                    return {'FINISHED'}
                    
        return {'PASS_THROUGH'}

    def cleanup_timer(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def execute(self, context):
        props = context.scene.geguchh_props
        backend_dir = os.path.normpath(props.backend_path)
        
        if state.is_downloading or state.is_setting_up:
            self.report({'WARNING'}, "Installation or setup is already running.")
            return {'CANCELLED'}
            
        os.makedirs(backend_dir, exist_ok=True)
        zip_path = os.path.join(backend_dir, "Geguchh_v16_hunyuan2.zip")
        
        # Start download
        self.report({'INFO'}, "Starting backend download...")
        self.download_thread = threading.Thread(
            target=download_backend_thread, 
            args=(props.download_url, zip_path)
        )
        self.download_thread.start()
        self.download_active = True
        
        # Register modal timer
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

# Operator: Start local silent FastAPI server
class GEGUCHH_OT_StartServer(bpy.types.Operator):
    bl_idname = "geguchh.start_server"
    bl_label = "Start Local Server"
    bl_description = "Start the silent backend server in the background"
    
    _timer = None
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            if state.server_status == "STARTING":
                props = context.scene.geguchh_props
                if is_port_open(props.api_port):
                    state.server_status = "RUNNING"
                    self.report({'INFO'}, f"Server successfully started on port {props.api_port}!")
                    context.window_manager.event_timer_remove(self._timer)
                    context.area.tag_redraw()
                    return {'FINISHED'}
                
                if state.server_process and state.server_process.poll() is not None:
                    state.server_status = "ERROR"
                    state.server_error = "Server process terminated unexpectedly."
                    self.report({'ERROR'}, state.server_error)
                    context.window_manager.event_timer_remove(self._timer)
                    context.area.tag_redraw()
                    return {'FINISHED'}
        return {'PASS_THROUGH'}

    def execute(self, context):
        props = context.scene.geguchh_props
        backend_dir = os.path.normpath(props.backend_path)
        
        if state.server_status == "RUNNING" or state.server_status == "STARTING":
            self.report({'WARNING'}, "Server is already active or starting.")
            return {'CANCELLED'}
            
        if not state.is_installed:
            self.report({'ERROR'}, "Backend not configured at specified path. Please configure it first.")
            return {'CANCELLED'}
            
        if is_port_open(props.api_port):
            self.report({'ERROR'}, f"Port {props.api_port} is already in use by another process.")
            return {'CANCELLED'}
            
        # Start server silently
        tools_dir = os.path.join(backend_dir, "tools")
        start_bat = os.path.join(tools_dir, "run_server_silent.bat")
        
        args_list = [
            f"--host 127.0.0.1",
            f"--port {props.api_port}",
            f"--model_path {props.model_path}",
            f"--device {props.device}"
        ]
        if props.enable_tex:
            args_list.append("--enable_tex")
            
        args_str = " ".join(args_list)
        
        with open(start_bat, "w") as f:
            f.write("@echo off\n")
            f.write("call environment.bat\n")
            f.write("cd /d ..\\code\n")
            f.write(f"%PYTHON% api_server.py {args_str}\n")
            
        state.server_status = "STARTING"
        state.server_error = ""
        
        try:
            state.server_process = subprocess.Popen(
                [start_bat],
                cwd=tools_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception as e:
            state.server_status = "ERROR"
            state.server_error = str(e)
            self.report({'ERROR'}, f"Could not start server: {e}")
            return {'FINISHED'}

# Operator: Stop local backend server
class GEGUCHH_OT_StopServer(bpy.types.Operator):
    bl_idname = "geguchh.stop_server"
    bl_label = "Stop Local Server"
    bl_description = "Stop the running backend server process"
    
    def execute(self, context):
        if state.server_status == "STOPPED":
            self.report({'WARNING'}, "Server is not running.")
            return {'CANCELLED'}
            
        if state.server_process:
            pid = state.server_process.pid
            try:
                if sys.platform == 'win32':
                    subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    state.server_process.terminate()
            except Exception as e:
                print(f"Error terminating server process: {e}")
                
            state.server_process = None
            
        try:
            props = context.scene.geguchh_props
            start_bat = os.path.join(os.path.normpath(props.backend_path), "tools", "run_server_silent.bat")
            if os.path.exists(start_bat):
                os.remove(start_bat)
        except Exception:
            pass
            
        state.server_status = "STOPPED"
        self.report({'INFO'}, "Server successfully stopped.")
        return {'FINISHED'}

# Operator: Generate Model / Apply texture
class GEGUCHH_OT_Generate3D(bpy.types.Operator):
    bl_idname = "geguchh.generate_3d"
    bl_label = "Generate 3D Model"
    bl_description = "Run generation using local backend server"
    
    _timer = None
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            if state.is_generating:
                context.area.tag_redraw()
                return {'PASS_THROUGH'}
                
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            
            if state.generation_error:
                self.report({'ERROR'}, f"Generation failed: {state.generation_error}")
                return {'FINISHED'}
                
            if state.generation_success_file:
                try:
                    filepath = state.generation_success_file
                    bpy.ops.import_scene.gltf(filepath=filepath)
                    os.unlink(filepath)
                    
                    self.report({'INFO'}, "Model successfully generated and imported!")
                    
                    if state.apply_to_selected and state.target_mesh_name:
                        target_obj = bpy.data.objects.get(state.target_mesh_name)
                        new_obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
                        
                        if target_obj and new_obj:
                            new_obj.location = target_obj.location
                            new_obj.rotation_euler = target_obj.rotation_euler
                            new_obj.scale = target_obj.scale
                            
                            target_obj.hide_set(True)
                            target_obj.hide_render = True
                            
                except Exception as e:
                    self.report({'ERROR'}, f"Error during model import: {e}")
                    
            return {'FINISHED'}
            
        return {'PASS_THROUGH'}

    def execute(self, context):
        props = context.scene.geguchh_props
        
        if state.server_status != "RUNNING":
            if not is_port_open(props.api_port):
                self.report({'ERROR'}, "Server is not running. Please start the server first.")
                return {'CANCELLED'}
                
        if state.is_generating:
            self.report({'WARNING'}, "Generation is already in progress.")
            return {'CANCELLED'}
            
        prompt = props.prompt
        image_path = props.image_path
        
        if not prompt and not image_path:
            self.report({'WARNING'}, "Please specify either a Text Prompt or an Image Path.")
            return {'CANCELLED'}
            
        payload = {
            "octree_resolution": props.octree_resolution,
            "num_inference_steps": props.num_inference_steps,
            "guidance_scale": props.guidance_scale,
            "texture": props.texture
        }
        
        selected_mesh = None
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                selected_mesh = obj
                break
                
        apply_to_selected = False
        target_mesh_name = ""
        
        if selected_mesh and props.texture:
            self.report({'INFO'}, f"Texturing selected mesh: {selected_mesh.name}")
            apply_to_selected = True
            target_mesh_name = selected_mesh.name
            
            temp_glb_file = tempfile.NamedTemporaryFile(delete=False, suffix=".glb")
            temp_glb_file.close()
            
            bpy.ops.export_scene.gltf(filepath=temp_glb_file.name, use_selection=True)
            with open(temp_glb_file.name, "rb") as file:
                mesh_data = file.read()
            os.unlink(temp_glb_file.name)
            
            payload["mesh"] = base64.b64encode(mesh_data).decode('utf-8')
            
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as file:
                img_data = file.read()
            payload["image"] = base64.b64encode(img_data).decode('utf-8')
        elif prompt:
            payload["text"] = prompt
            
        api_url = f"http://localhost:{props.api_port}"
        
        self.gen_thread = threading.Thread(
            target=generate_model_thread, 
            args=(api_url, payload, apply_to_selected, target_mesh_name)
        )
        self.gen_thread.start()
        
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

# =========================================================================
# User Interface
# =========================================================================
class GEGUCHH_PT_HunyuanPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Geguchh Hunyuan2'
    bl_label = 'Hunyuan2 3D Generator'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.geguchh_props
        
        # Initialize status cache once on drawing if not yet set
        if not state.status_initialized:
            update_status_cache(context=context)
            
        # 1. Path Configuration
        box_path = layout.box()
        box_path.label(text="Installation Path Config", icon='FILE_FOLDER')
        box_path.prop(props, "backend_path", text="Backend Dir")
        
        # 2. Installation and backend setup section
        box = layout.box()
        box.label(text="Backend Configuration Status", icon='PREFERENCES')
        
        # 2.1 Backend check (reads cached state directly - no disk lag!)
        if state.is_installed:
            box.label(text="Backend status: Configured", icon='CHECKMARK')
        else:
            box.label(text="Backend status: Not Configured", icon='ERROR')
            
        # 2.2 Model Weights check (reads cached state directly - no disk lag!)
        if state.weights_cached:
            box.label(text="Model weights: Cached (Ready)", icon='CHECKMARK')
        else:
            box.label(text="Model weights: Not Detected", icon='INFO')
            box.label(text="  (Will auto-download on first run)")
            
        # If backend not configured, show install tools
        if not state.is_installed:
            box.prop(props, "download_url", text="Zip URL")
            
            if state.is_downloading:
                box.label(text=f"Downloading backend: {state.download_percent:.1f}%")
                row = box.row()
                row.progress(factor=state.download_percent / 100.0)
            elif state.is_setting_up:
                box.label(text=f"Status: {state.setup_status}")
                log_box = box.box()
                log_box.label(text="Setup logs:")
                recent_logs = state.setup_log[-10:] if state.setup_log else ["Initializing..."]
                for line in recent_logs:
                    log_box.label(text=line)
            else:
                box.operator("geguchh.configure_backend", icon='IMPORT', text="Download & Configure Backend")
                
        # 3. Server Controller
        if state.is_installed:
            box = layout.box()
            box.label(text="Backend Server Controller", icon='CONSOLE')
            
            if state.server_status == "RUNNING":
                box.label(text=f"Server Port: {props.api_port} - RUNNING", icon='PLAY')
                box.operator("geguchh.stop_server", icon='QUIT', text="Stop local Server")
            elif state.server_status == "STARTING":
                box.label(text="Server: Starting up...", icon='FILE_REFRESH')
            else:
                box.label(text="Server: STOPPED", icon='PAUSE')
                box.prop(props, "api_port")
                box.prop(props, "model_path")
                box.prop(props, "device")
                box.prop(props, "enable_tex")
                box.operator("geguchh.start_server", icon='PLAY', text="Start local Server")
                
            if state.server_error:
                box.label(text=f"Error: {state.server_error}", icon='ERROR')
                
        # 4. Generation Form
        if state.is_installed and state.server_status == "RUNNING":
            box = layout.box()
            box.label(text="Generate 3D Model", icon='MESH_MONKEY')
            
            box.prop(props, "prompt")
            box.prop(props, "image_path")
            
            adv = box.box()
            adv.label(text="Generation Settings", icon='SETTINGS')
            adv.prop(props, "guidance_scale")
            adv.prop(props, "num_inference_steps")
            adv.prop(props, "octree_resolution")
            adv.prop(props, "texture")
            
            if state.is_generating:
                box.label(text=f"Generating: {state.generation_status}")
                row = box.row()
                row.progress(factor=state.generation_progress / 100.0)
            else:
                box.operator("geguchh.generate_3d", icon='DUPLICATE', text="Generate 3D inside Blender")

# =========================================================================
# Registration
# =========================================================================
classes = (
    GeguchhAddonProperties,
    GEGUCHH_OT_ConfigureBackend,
    GEGUCHH_OT_StartServer,
    GEGUCHH_OT_StopServer,
    GEGUCHH_OT_Generate3D,
    GEGUCHH_PT_HunyuanPanel
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.geguchh_props = bpy.props.PointerProperty(type=GeguchhAddonProperties)

def unregister():
    if state.server_status == "RUNNING" and state.server_process:
        try:
            pid = state.server_process.pid
            if sys.platform == 'win32':
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                state.server_process.terminate()
        except Exception:
            pass
            
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.geguchh_props

if __name__ == "__main__":
    register()
