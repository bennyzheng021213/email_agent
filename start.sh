#!/bin/bash

# Email Agent Startup Script

echo "========================================"
echo "      Email Agent Startup Script"
echo "========================================"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python Version: $python_version"

if [[ "$python_version" < "3.8" ]]; then
    echo "Error: Python 3.8 or higher is required"
    exit 1
fi

# Check virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Warning: Virtual environment not found, using system Python"
    read -p "Create virtual environment? (y/n): " create_venv
    if [[ $create_venv == "y" ]]; then
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
    fi
fi

# Check dependencies
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt file not found"
    exit 1
fi

echo "Checking dependencies..."
pip install -r requirements.txt

# Check environment variables
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found"
    echo "Creating from example file..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Please edit .env file to configure API keys"
        exit 1
    else
        echo "Error: .env.example file not found"
        exit 1
    fi
fi

# Check Gmail credentials
if [ ! -f "credentials.json" ]; then
    echo "Warning: credentials.json file not found"
    echo "Please configure Gmail API following the README.md instructions"
    exit 1
fi

# Run mode selection
echo ""
echo "Select run mode:"
echo "1) Single run (process current unread emails)"
echo "2) Continuous run (background monitoring)"
echo "3) View help"
echo ""

read -p "Enter option (1-3): " mode

case $mode in
    1)
        echo "Starting single run mode..."
        python main.py --mode once
        ;;
    2)
        echo "Starting continuous run mode..."
        read -p "Check interval (seconds) [default 15]: " interval
        interval=${interval:-15}
        echo "Checking for new emails every ${interval} seconds"
        python main.py --mode continuous --interval $interval
        ;;
    3)
        echo "Showing help information..."
        python main.py --help
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo "      Program execution completed"
echo "========================================"
