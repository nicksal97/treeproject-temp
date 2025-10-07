#!/bin/bash

# Setup script for tree detection API
# Uses conda because GDAL is a pain to install otherwise

set -e

echo "Setting up tree detection API with conda..."
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# make sure conda is available
echo "Checking for conda..."
if ! command -v conda &> /dev/null; then
    echo -e "${RED}Error: conda not found${NC}"
    echo "Install from https://docs.conda.io/en/latest/miniconda.html"
    echo "Or just use setup.sh instead"
    exit 1
fi

conda_version=$(conda --version 2>&1)
echo -e "${GREEN}Found $conda_version${NC}"

# Initialize conda for bash
if [ -f "$HOME/.bashrc" ]; then
    eval "$(conda shell.bash hook)"
elif [ -f "$HOME/.bash_profile" ]; then
    eval "$(conda shell.bash hook)"
fi

# check if env exists already
ENV_NAME="tree-detection-api"
echo ""
echo "Looking for existing environment..."
if conda env list | grep -q "^${ENV_NAME} "; then
    echo -e "${YELLOW}Warning: environment '${ENV_NAME}' already exists${NC}"
    read -p "Remove and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing old environment..."
        conda env remove -n ${ENV_NAME} -y
        echo -e "${GREEN}Done${NC}"
    else
        echo "Keeping existing environment"
    fi
fi

# create/update the environment
if ! conda env list | grep -q "^${ENV_NAME} "; then
    echo ""
    echo "Creating conda environment (this will take a while)..."
    conda env create -f environment.yml
    echo -e "${GREEN}Environment created${NC}"
else
    echo ""
    echo "Updating environment..."
    conda env update -f environment.yml --prune
    echo -e "${GREEN}Updated${NC}"
fi

# activate it
echo ""
echo "Activating environment..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ${ENV_NAME}

# test GDAL
echo ""
echo "Testing GDAL..."
if python -c "from osgeo import gdal; print(f'GDAL version: {gdal.__version__}')" 2>/dev/null; then
    echo -e "${GREEN}GDAL OK${NC}"
else
    echo -e "${RED}GDAL failed - check your environment.yml${NC}"
    exit 1
fi

# check other imports
echo "Checking dependencies..."
python -c "import flask, torch, ultralytics, rasterio" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Dependencies OK${NC}"
else
    echo -e "${RED}Some imports failed${NC}"
    exit 1
fi

# check for models
echo ""
echo "Checking for models..."

mkdir -p models/summer
mkdir -p models/winter

summer_models=$(ls models/summer/*.pt 2>/dev/null | wc -l)
winter_models=$(ls models/winter/*.pt 2>/dev/null | wc -l)

if [ "$summer_models" -eq 0 ]; then
    echo -e "${YELLOW}No summer models found - add them to models/summer/${NC}"
    echo "Example: cp /path/to/model.pt models/summer/best.pt"
else
    echo -e "${GREEN}Found $summer_models summer model(s)${NC}"
fi

if [ "$winter_models" -eq 0 ]; then
    echo -e "${YELLOW}No winter models found - add them to models/winter/${NC}"
    echo "Example: cp /path/to/model.pt models/winter/best.pt"
else
    echo -e "${GREEN}Found $winter_models winter model(s)${NC}"
fi

# setup directories
echo ""
mkdir -p uploads
mkdir -p outputs
mkdir -p temp
echo "Directories ready"

# done
echo ""
echo "=========================================="
echo -e "${GREEN}Setup complete!${NC}"
echo "=========================================="
echo ""
echo "To use:"
echo ""
echo "1. Activate environment:"
echo "   conda activate ${ENV_NAME}"
echo ""
echo "2. Make sure you have models in place:"
echo "   models/summer/best.pt"
echo "   models/winter/best.pt"
echo ""
echo "3. Run the server:"
echo "   python run.py"
echo ""
echo "4. Test it:"
echo "   curl http://localhost:5000/health"
echo ""
echo "To deactivate: conda deactivate"
echo ""
