# Geguchh Hunyuan2 3D Generator

A professional, lightweight Blender addon and its standalone FastAPI backend server for generating 3D models and texturing existing meshes locally using **Tencent Hunyuan3D-2**.

---

## Repository Contents

- **`hunyuan3d_generator.zip`** (Addon, ~7.5 KB): The lightweight Blender addon.
- **`build_addon.py`**: Python script to package the addon source code.
- **`rebrand_and_zip.py`**: Python script to compile and rebrand the backend workspace.
- **`README.md`**: This guide.

*Note: The heavy backend zip (`Geguchh_v16_hunyuan2.zip`, 334 MB) should be uploaded to your GitHub repository's **Releases** section so the addon can download it on demand.*

---

## 🚀 Quick Start Guide

### Step 1: Install the Blender Addon
1. Open Blender.
2. Go to **Edit > Preferences > Addons**.
3. Click **Install...** in the top right corner and select `hunyuan3d_generator.zip`.
4. Check the box to enable **Geguchh Hunyuan2 3D Generator**.
5. Close Preferences. A new tab named **Geguchh Hunyuan2** will appear in the sidebar of your 3D Viewport (`N` key).

### Step 2: Configure the Backend (Two Options)

#### Option A: Automatic Setup (Recommended for buyers)
1. Go to the **Geguchh Hunyuan2** tab in the Blender sidebar.
2. Under **Installation Path Config**, choose where you want to install the backend (or keep the default).
3. If you have uploaded `Geguchh_v16_hunyuan2.zip` to your own GitHub, enter your custom URL in the **Zip URL** field.
4. Click **Download & Configure Backend**.
5. The addon will download the zip, extract it, install Python packages, configure PyTorch (with CUDA 12.8 acceleration), and verify dependencies in the background. Progress and logs are shown in real-time.

#### Option B: Linking an Existing Backend
If you already have the backend folder extracted elsewhere on your machine:
1. In the **Geguchh Hunyuan2** panel, set **Backend Folder** to your existing folder (e.g. `C:\v16_hunyuan2-stableprojectorz`).
2. The addon status will immediately update to **Status: Installed & Configured (Ready)**.

---

## 🎛️ Running the Server

1. Set the **Server Port** (default: `8081`).
2. Choose your hardware acceleration (CUDA/GPU is recommended).
3. Select your model size (`Mini` is fast, `Full` is high quality).
4. Enable/disable **Load Texturing Pipeline** (disabling saves ~6 GB VRAM).
5. Click **Start Local Server**. The server runs silently in the background (no cmd window pops up).
6. Once the status shows **RUNNING**, you are ready to generate models.

---

## 🎨 Generating 3D Models inside Blender

### Text-to-3D or Image-to-3D
1. Enter your description in **Text Prompt** OR select an image path in **Image Path**.
2. Set generation parameters (Inference Steps, Guidance Scale, Octree Resolution).
3. Click **Generate 3D inside Blender**. The model will generate asynchronously (without freezing your screen) and import into your scene.

### Mesh Texturing
1. Select a mesh in your viewport.
2. Provide a **Text Prompt** describing the desired textures, or select a reference image in **Image Path**.
3. Check the **Generate Texture** box.
4. Click **Generate 3D inside Blender**. The addon will upload the mesh, texture it on the server, import the textured GLB, and align it perfectly to your selected mesh's position and scale.

---

## 🛠️ Standalone Backend Execution (CLI/Web UI)

The backend can also be run independently of Blender. Extract `Geguchh_v16_hunyuan2.zip` and run:

- **FastAPI Backend (StableProjectorz Compatible)**:
  Run `tools/geguchh-internal.bat` or use scripts in `run-geguchh_(faster)/` (runs on port `7960`).
- **Gradio Web Application**:
  Use scripts in `run-browser_(slower)/` to open a local browser tab (runs on port `7860`).
