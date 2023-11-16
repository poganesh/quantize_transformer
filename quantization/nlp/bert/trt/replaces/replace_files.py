import os
import shutil
import site
import logging


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def copy(source_file,dest_path):
    if os.path.exists(source_file):
      logging.info(f"copying {source_file} to {dest_path}")
      shutil.copy(source_file, dest_path)
    else:
      logging.fatal(f"{source_file} does not exist.")


site_paths = site.getsitepackages()
ort_site_paths = []

def copy_tree(dest_name, replace_path):
    for site_path in site_paths:
        dest_site_path = os.path.join(site_path, dest_name)
        if os.path.exists(dest_site_path):
            shutil.copytree(replace_path, dest_site_path, dirs_exist_ok=True)
            print(f"{replace_path} is copied to {dest_site_path}")
            ort_site_paths.append(site_path)

def copy_file(dest_name, replace_file):
    for site_path in site_paths:
        dest_site_path = os.path.join(site_path, dest_name)
        if os.path.exists(dest_site_path):
            shutil.copy(replace_file, dest_site_path)
            print(f"{replace_file} is copied to {dest_site_path}")

copy_tree("onnxruntime\\capi", "capi")

# copy providers
if ort_site_paths:
    for ort_site_path in ort_site_paths:
        provider_path = os.path.join(ort_site_path, "onnxruntime\\providers\\tvm")
        if not os.path.exists(provider_path):
            os.makedirs(provider_path)
        copy("providers\\tvm\\__init__.py", provider_path)
        copy("providers\\tvm\\ort.py", provider_path)

# copy tvm aie control json
tvm_json_path = "C:\\Windows\\System32\\AMD\\.tvm\\aie"
if not os.path.exists(tvm_json_path):
    os.makedirs(tvm_json_path)
for file_name in os.listdir("tvm"):
    source_dir = os.path.join("tvm", file_name)
    copy(source_dir, tvm_json_path)
