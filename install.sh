#!/bin/bash

set -e
set -u

INSTALL_MEIC=0
INSTALL_CIRFIX=0
INSTALL_RTLREPAIR=0

VERILATOR_VER="4.228"

MEIC_REQUIREMENTS_FILE="resources/requirements/meic.txt"
CIRFIX_REQUIREMENTS_FILE="resources/requirements/cirfix.txt"
RTLREPAIR_REQUIREMENTS_FILE="resources/requirements/rtlrepair.txt"
CIRFIX_PATCH_FILE="resources/patches/cirfix/patch.py"

BITWUZLA_DIR="bitwuzla"
OSDD_DIR="tools/rtlrepair/osdd"
SYNTH_DIR="tools/rtlrepair/synth"
VERILATOR_DIR="verilator-$VERILATOR_VER"

ENABLE_YICES=1
ENABLE_BITWUZLA=0
ENABLE_VERILATOR=1
ENABLE_OSDD=1
ENABLE_SYNTH=1

PYTHON=python3

set -e

usage() {
    echo "Usage: $0 [--meic] [--cirfix] [--rtlrepair]"
    echo "  --meic      Install dependencies for MEIC"
    echo "  --cirfix    Install dependencies for CirFix"
    echo "  --rtlrepair Install dependencies for RTL-Repair"
    exit 1
}

if [ "$#" -eq 0 ]; then
    INSTALL_MEIC=1
    INSTALL_CIRFIX=1
    INSTALL_RTLREPAIR=1
else
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --meic)
                INSTALL_MEIC=1
                ;;
            --cirfix)
                INSTALL_CIRFIX=1
                ;;
            --rtlrepair)
                INSTALL_RTLREPAIR=1
                ;;
            *)
                usage
                ;;
        esac
        shift
    done
fi

pip install pandas
apt install -y iverilog

if [ "$INSTALL_MEIC" = "1" ]; then
    if [ -f "$MEIC_REQUIREMENTS_FILE" ]; then
        echo "Installing dependencies for MEIC ..."
        pip install -r "$MEIC_REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            echo "Failed to install MEIC dependencies."
            exit 1
        fi
    fi
fi

if [ "$INSTALL_CIRFIX" = "1" ]; then
    if [ -f "$CIRFIX_REQUIREMENTS_FILE" ]; then
        echo "Installing dependencies for CirFix ..."
        pip install -r "$CIRFIX_REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            echo "Failed to install CirFix dependencies."
            exit 1
        fi
    fi
    $PYTHON $CIRFIX_PATCH_FILE
fi

if [ "$INSTALL_RTLREPAIR" = "1" ]; then
    if [ -f "$RTLREPAIR_REQUIREMENTS_FILE" ]; then
        echo "Installing dependencies for RTL-Repair ..."
        pip install -r "$RTLREPAIR_REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            echo "Failed to install RTL-Repair dependencies."
            exit 1
        fi
    fi

    apt install -y yosys cmake libgmp-dev cadical cargo flex bison
    pip install meson ninja

    if [ "$ENABLE_BITWUZLA" = "1" ]; then
        echo "Installing Bitwuzla ..."
        rm -rf "$BITWUZLA_DIR"
        git clone https://github.com/bitwuzla/bitwuzla.git "$BITWUZLA_DIR" && \
        (
            cd "$BITWUZLA_DIR" && \
            ./configure.py && cd build && ninja install
        )
        echo "Bitwuzla installed successfully!"
    fi

    if [ "$ENABLE_YICES" = "1" ]; then
        echo "Installing yices2 ..."
        add-apt-repository -y ppa:sri-csl/formal-methods
        apt-get update
        apt-get install -y yices2-dev
    fi

    if [ "$ENABLE_VERILATOR" = "1" ]; then
        echo "Installing Verilator ..."
        rm -rf "$VERILATOR_DIR"
        wget -O verilator.tar.gz "https://github.com/verilator/verilator/archive/refs/tags/v${VERILATOR_VER}.tar.gz" && (
            tar zxvf verilator.tar.gz && cd "$VERILATOR_DIR" && autoconf && ./configure && make -j "$(nproc)" && make install
        ) || { echo "Failed to install Verilator."; exit 1; }
        rm -rf "$VERILATOR_DIR" verilator.tar.gz
        echo "Verilator installed successfully!"
    fi

    if [ "$ENABLE_OSDD" = "1" ]; then
        echo "Installing OSDD ..."
        cargo build --release --manifest-path "$OSDD_DIR/Cargo.toml" && echo "OSDD installed successfully!"
    fi

    if [ "$ENABLE_SYNTH" = "1" ]; then
        echo "Installing SYNTH ..."
        cargo build --release --manifest-path "$SYNTH_DIR/Cargo.toml" && echo "SYNTH installed successfully!"
    fi
fi

echo "Installation completed successfully."
