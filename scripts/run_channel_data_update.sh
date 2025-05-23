#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment if it exists
if [ -d "$SCRIPT_DIR/../venv" ]; then
    source "$SCRIPT_DIR/../venv/bin/activate"
fi

# Run the Python script
python "$SCRIPT_DIR/populate_channel_data.py"
