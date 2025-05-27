#!/usr/bin/env bash

SCRIPT_NAME=$(basename "$0")
SUPPORTED_TYPES=("cirfix" "rtlrepair" "meic")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function show_help {
    echo "Usage: $SCRIPT_NAME [-t TYPE] [-h]"
    echo ""
    echo "Options:"
    echo "  -t TYPE     Specify the repair framework type"
    echo "              Supported types: ${SUPPORTED_TYPES[*]}"
    echo "  -h          Show this help message and exit"
    echo ""
    echo "Examples:"
    echo "  $SCRIPT_NAME -t cirfix    # Run with CirFix framework"
    echo "  $SCRIPT_NAME              # Run with default settings"
    exit 0
}

function validate_type {
    local type=$1
    if [[ ! " ${SUPPORTED_TYPES[*]} " =~ " ${type} " ]]; then
        echo -e "${RED}Error: Invalid type '${type}'. Supported types are: ${SUPPORTED_TYPES[*]}${NC}" >&2
        exit 1
    fi
}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR" || {
    echo -e "${RED}Error: Failed to change directory to $SCRIPT_DIR${NC}" >&2
    exit 1
}

TYPE=""
PYTHON=python3
PYTHON_SCRIPT="scripts/rtlfixbench.py"

while [[ $# -gt 0 ]]; do
    case $1 in
        -t)
            if [[ -z $2 ]]; then
                echo -e "${RED}Error: -t requires a type argument${NC}" >&2
                show_help
                exit 1
            fi
            TYPE="$2"
            validate_type "$TYPE"
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        -*)
            echo -e "${RED}Error: Unknown option $1${NC}" >&2
            show_help
            exit 1
            ;;
        *)
            echo -e "${RED}Error: Unexpected argument $1${NC}" >&2
            show_help
            exit 1
            ;;
    esac
done

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo -e "${RED}Error: Python script not found at $PYTHON_SCRIPT${NC}" >&2
    exit 1
fi

ARGS=()
[[ -n "$TYPE" ]] && ARGS+=("-t" "$TYPE")

echo -e "${YELLOW}Running RTLFixBench with ${TYPE:-default settings}...${NC}"
if ! $PYTHON "$PYTHON_SCRIPT" "${ARGS[@]}"; then
    echo -e "${RED}Error: Failed to execute the Python script${NC}" >&2
    exit 1
fi

exit 0