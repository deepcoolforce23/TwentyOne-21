#!/usr/bin/env python3
"""
Module Installer
Installs all external modules needed for the projects in this workspace.
"""

import subprocess
import sys
import importlib

# List of external modules needed for twenty_one.py
MODULES_TO_INSTALL = [
    "websockets",    # 21 v1.0 - online game server
]

def install_module(module_name):
    """Install a single module using pip."""
    try:
        print(f"Installing {module_name}...", end=" ")
        subprocess.check_call([sys.executable, "-m", "pip", "install", module_name, "-q"])
        print("✓ Success!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed!")
        return False

def check_module_installed(module_name):
    """Check if a module is already installed."""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False

def main():
    print("=" * 50)
    print("  Module Installer for twenty_one.py")
    print("=" * 50)
    print()
    
    # First, upgrade pip
    print("Upgrading pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    print("✓ pip upgraded!")
    print()
    
    # Track results
    installed = []
    failed = []
    already_installed = []
    
    # Install each module
    for module in MODULES_TO_INSTALL:
        if check_module_installed(module):
            print(f"✓ {module} already installed!")
            already_installed.append(module)
        else:
            if install_module(module):
                installed.append(module)
            else:
                failed.append(module)
    
    # Summary
    print()
    print("=" * 50)
    print("  INSTALLATION SUMMARY")
    print("=" * 50)
    
    if already_installed:
        print(f"\nAlready installed ({len(already_installed)}):")
        for mod in already_installed:
            print(f"  • {mod}")
    
    if installed:
        print(f"\nSuccessfully installed ({len(installed)}):")
        for mod in installed:
            print(f"  • {mod}")
    
    if failed:
        print(f"\nFailed to install ({len(failed)}):")
        for mod in failed:
            print(f"  • {mod}")
        print("\nPlease try installing failed modules manually:")
        print(f"  pip install <module_name>")
    
    if not failed:
        print("\n✓ All modules installed successfully!")
    
    print()
    print("You can now run the projects!")
    
    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
