#!/bin/bash
# Quick Start Script for Error Analyzer

set -e

echo "🚀 Error Analyzer Setup"
echo "======================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python 3.10+ required (found: $PYTHON_VERSION)"
    exit 1
fi

echo "✅ Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Setup .env if not exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env with your credentials:"
    echo "   - CLICKHOUSE_PASSWORD"
    echo "   - OPENAI_API_KEY"
    echo ""
    read -p "Press Enter to edit .env now (or Ctrl+C to exit)..."
    ${EDITOR:-nano} .env
fi

# Validate setup
echo ""
echo "🧪 Validating setup..."
python3 -c "
from error_analyzer import Settings
try:
    settings = Settings()
    print('✅ Configuration loaded successfully')
    
    # Check for placeholder values
    if settings.OPENAI_API_KEY.get_secret_value().startswith('sk-...'):
        print('⚠️  WARNING: Using placeholder API key')
    
    if settings.CLICKHOUSE_PASSWORD.get_secret_value() == '':
        print('⚠️  WARNING: Empty ClickHouse password')
        
except Exception as e:
    print(f'❌ Configuration error: {e}')
    exit(1)
"

# Run tests
echo ""
read -p "Run tests? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧪 Running tests..."
    pytest test_error_analyzer.py -v --tb=short
fi

# Final instructions
echo ""
echo "✅ Setup complete!"
echo ""
echo "📖 Next steps:"
echo "   1. Ensure SigNoz/ClickHouse is running"
echo "   2. Run: python error_analyzer.py"
echo "   3. Check output in: analysis_*.json"
echo ""
echo "📚 Documentation: cat README.md"
echo "🐛 Troubleshooting: See README.md > Troubleshooting"
