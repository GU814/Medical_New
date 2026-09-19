#!/usr/bin/env python3
"""
Offline Setup Script for Medical Consultation AI
This script helps prepare the system for offline operation by:
1. Downloading Ollama installer
2. Downloading required models
3. Setting up the directory structure
"""

import os
import sys
import subprocess
import requests
import time
from pathlib import Path

def download_file(url, filepath):
    """Download a file from URL to local path"""
    try:
        print(f"Downloading {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded to {filepath}")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def setup_ollama_installer():
    """Download Ollama Windows installer"""
    installer_dir = Path("installer")
    installer_dir.mkdir(exist_ok=True)

    installer_path = installer_dir / "OllamaSetup.exe"

    if installer_path.exists():
        print("Ollama installer already exists")
        return True

    # Download Ollama installer
    url = "https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe"
    return download_file(url, installer_path)

def setup_models():
    """Download and setup required models"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)

    print("\nSetting up Ollama models...")
    print("Note: This requires Ollama to be installed and running")

    # Required models
    models = [
        "deepseek-r1:8b",
        "nomic-embed-text"
    ]

    for model in models:
        print(f"\nPulling model: {model}")
        try:
            result = subprocess.run(['ollama', 'pull', model], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Successfully pulled {model}")
            else:
                print(f"Failed to pull {model}: {result.stderr}")
        except Exception as e:
            print(f"Error pulling {model}: {e}")

def check_ollama_installed():
    """Check if Ollama is installed"""
    try:
        result = subprocess.run(['where', 'ollama'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def start_ollama_service():
    """Start Ollama service"""
    try:
        subprocess.Popen(['ollama', 'serve'], shell=True)
        print("Ollama service started")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"Failed to start Ollama service: {e}")
        return False

def main():
    print("=== Medical Consultation AI - Offline Setup ===\n")

    # Step 1: Download Ollama installer
    print("Step 1: Setting up Ollama installer...")
    if not setup_ollama_installer():
        print("Failed to download Ollama installer")
        return

    # Step 2: Check if Ollama is installed
    print("\nStep 2: Checking Ollama installation...")
    if not check_ollama_installed():
        print("Ollama is not installed.")
        print("Please run the installer from installer/OllamaSetup.exe")
        print("Then run this script again.")
        return

    print("Ollama is already installed")

    # Step 3: Start Ollama service
    print("\nStep 3: Starting Ollama service...")
    if not start_ollama_service():
        print("Failed to start Ollama service")
        return

    # Step 4: Download models
    print("\nStep 4: Setting up models...")
    setup_models()

    print("\n=== Setup Complete ===")
    print("You can now run the medical consultation AI in offline mode")

if __name__ == "__main__":
    main()