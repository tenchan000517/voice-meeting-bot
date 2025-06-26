#!/bin/bash
# Git Bash compatible setup script

echo "Creating Windows-compatible Python environment..."

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.8+ first."
    exit 1
fi

# Remove old venv if exists
if [ -d "venv" ]; then
    echo "Removing old virtual environment..."
    rm -rf venv
fi

# Create new virtual environment
echo "Creating virtual environment..."
python -m venv venv

# Activate virtual environment (Git Bash)
echo "Activating virtual environment..."
source venv/Scripts/activate

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

echo ""
echo "Setup complete! To activate the environment:"
echo "  source venv/Scripts/activate"
echo ""
echo "To run the API:"
echo "  python main.py"
echo ""