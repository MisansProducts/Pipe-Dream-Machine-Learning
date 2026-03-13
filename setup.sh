#!/bin/bash
# Pipe Dream Setup Script

set -e

show_help() {
    echo "Usage: ./setup.sh [OPTIONS]"
    echo
    echo "Options:"
    echo "  --all      Run all setup steps"
    echo "  --env      Create/update .env file"
    echo "  --py       Setup Python virtual environment"
    echo "  --dev      Same as running --env --py"
    echo "  --help     Show this help message"
    echo
    echo "Examples:"
    echo "  ./setup.sh --all"
    echo "  ./setup.sh --env --py"
}

setup_env() {
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
}

setup_py() {
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv .venv
    else
        echo ".venv already exists - skipping"
    fi

    if [ ! -d "models" ]; then
        echo "Creating models directory..."
        mkdir models
    else
        echo "models directory already exists - skipping"
    fi

    echo "Activating virtual environment and installing dependencies..."
    source .venv/bin/activate
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
}

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

RUN_ENV=false
RUN_PY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            RUN_ENV=true
            RUN_PY=true
            ;;
        --env)
            RUN_ENV=true
            ;;
        --py)
            RUN_PY=true
            ;;
        --dev)
            RUN_ENV=true
            RUN_PY=true
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

if [ "$RUN_ENV" = true ]; then
    setup_env
fi

if [ "$RUN_PY" = true ]; then
    setup_py
fi

if [ "$RUN_ENV" = false ] && [ "$RUN_PY" = false ]; then
    show_help
fi

echo
echo "Setup complete! Activate with: source .venv/bin/activate"
