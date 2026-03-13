#!/bin/bash

# Activate venv
source /home/zj/Workspace/hydromet_weather_app/venv/bin/activate

# Change to project directory
cd /home/zj/Workspace/hydromet_weather_app/backend/py

# Run the Python script with arguments
python data_pipeline_24h.py "$@"