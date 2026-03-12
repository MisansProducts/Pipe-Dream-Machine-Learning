#!/bin/bash
# Pipe Dream Setup Script

set -e

echo "Checking for existing environment files..."

# Root .env (only if it doesn't exist)
if [ ! -f ".env" ]; then
    echo "Creating .env..."
    cat > .env << 'EOF'
# --- Database Configuration ---
MONGO_URI=YOUR_MONGO_URI_HERE
DB_NAME=weather_db
EOF
else
    echo ".env already exists - skipping"
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo ".venv already exists - skipping"
fi

# Create models directory
if [ ! -d "models" ]; then
    echo "Creating models directory..."
    mkdir models
else
    echo "models directory already exists - skipping"
fi

# Activate virtual environment and install dependencies
echo "Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo
echo "Setup complete! Activate with: source .venv/bin/activate"