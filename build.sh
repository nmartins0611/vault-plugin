#!/bin/bash
#
# Build and install the HashiCorp Vault EDA plugin
#
# Usage:
#   ./build.sh            # Build and install
#   ./build.sh --clean    # Clean build artifacts
#   ./build.sh --test     # Build, install, and run basic tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Clean build artifacts
clean() {
    print_info "Cleaning build artifacts..."
    rm -f *.tar.gz
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    print_info "Clean complete"
}

# Build the collection
build() {
    print_info "Building collection..."

    # Verify required files exist
    if [ ! -f "galaxy.yml" ]; then
        print_error "galaxy.yml not found"
        exit 1
    fi

    if [ ! -f "extensions/eda/plugins/event_source/vault_events.py" ]; then
        print_error "Plugin file not found"
        exit 1
    fi

    # Build collection
    ansible-galaxy collection build --force

    # Find the built tarball
    TARBALL=$(ls -t hashicorp-vault-*.tar.gz 2>/dev/null | head -n1)

    if [ -z "$TARBALL" ]; then
        print_error "Build failed - no tarball created"
        exit 1
    fi

    print_info "Build successful: $TARBALL"
}

# Install the collection
install() {
    print_info "Installing collection..."

    # Find the built tarball
    TARBALL=$(ls -t hashicorp-vault-*.tar.gz 2>/dev/null | head -n1)

    if [ -z "$TARBALL" ]; then
        print_error "No tarball found - run build first"
        exit 1
    fi

    # Install collection
    ansible-galaxy collection install "$TARBALL" --force

    # Verify installation
    if ansible-galaxy collection list | grep -q "hashicorp.vault"; then
        print_info "Installation successful"
    else
        print_error "Installation verification failed"
        exit 1
    fi
}

# Check Python dependencies
check_deps() {
    print_info "Checking Python dependencies..."

    if ! python3 -c "import websockets" 2>/dev/null; then
        print_warn "websockets not installed"
        print_info "Installing dependencies..."
        pip install -r requirements.txt
    fi

    if ! python3 -c "import aiohttp" 2>/dev/null; then
        print_warn "aiohttp not installed"
        print_info "Installing dependencies..."
        pip install -r requirements.txt
    fi

    print_info "Dependencies OK"
}

# Run basic tests
test() {
    print_info "Running basic tests..."

    # Test 1: Import plugin
    print_info "Test 1: Importing plugin module..."
    python3 << 'EOF'
import sys
import os

# Add plugin directory to path
sys.path.insert(0, 'extensions/eda/plugins/event_source')

try:
    import vault_events
    print("✓ Plugin module imported successfully")

    # Check main function exists
    if hasattr(vault_events, 'main'):
        print("✓ main() function found")
    else:
        print("✗ main() function not found")
        sys.exit(1)

    # Check classes exist
    classes = ['VaultAuthenticator', 'VaultWebSocketClient', 'ReconnectionManager', 'EventProcessor']
    for cls in classes:
        if hasattr(vault_events, cls):
            print(f"✓ {cls} class found")
        else:
            print(f"✗ {cls} class not found")
            sys.exit(1)

except ImportError as e:
    print(f"✗ Failed to import plugin: {e}")
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_info "All tests passed"
    else
        print_error "Tests failed"
        exit 1
    fi
}

# Print usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Build and install the HashiCorp Vault EDA plugin.

Options:
    --clean     Clean build artifacts
    --test      Run tests after build
    --help      Show this help message

Examples:
    $0                  # Build and install
    $0 --clean          # Clean only
    $0 --test           # Build, install, and test

EOF
}

# Main script
main() {
    cd "$(dirname "$0")"

    case "${1:-}" in
        --clean)
            clean
            ;;
        --test)
            check_deps
            clean
            build
            install
            test
            ;;
        --help)
            usage
            ;;
        "")
            check_deps
            build
            install
            print_info "Done! Collection installed successfully."
            print_info "Try: ansible-galaxy collection list | grep vault"
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
}

main "$@"
