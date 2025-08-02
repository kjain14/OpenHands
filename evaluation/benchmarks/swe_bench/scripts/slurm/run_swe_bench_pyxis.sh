#!/bin/bash
# SWE-Bench evaluation script for SLURM with Pyxis (inference only)
# This script runs natively on the host but uses Pyxis containers for each instance
# SBATCH directives are handled dynamically by the launcher script

# Parse command line arguments
MODEL_CONFIG=$1
AGENT=$2
DATASET=$3
SPLIT=$4
MODE=${5:-swe}
MAX_ITER=${6:-100}

if [ -z "$MODEL_CONFIG" ] || [ -z "$AGENT" ] || [ -z "$DATASET" ] || [ -z "$SPLIT" ]; then
    echo "Usage: $0 MODEL_CONFIG AGENT DATASET SPLIT [MODE] [MAX_ITER]"
    echo "Example: $0 llm-config.json CodeActAgent princeton-nlp/SWE-bench_Lite test"
    exit 1
fi

# Set up paths
export OPENHANDS_ROOT=$(realpath $(dirname $0)/../../../../../)
export WORK_DIR=$PWD

# Create log directories
mkdir -p slurm_logs
mkdir -p evaluation_outputs/swe_bench_pyxis

# Export environment variables for the container
export EVAL_OUTPUT_DIR="/workspace/evaluation_outputs/swe_bench_pyxis/job_${SLURM_ARRAY_JOB_ID}"

# Get instance ID for this array task
INSTANCE_LIST_FILE="${WORK_DIR}/evaluation_outputs/swe_bench_pyxis/job_${SLURM_ARRAY_JOB_ID}/instance_list.json"

# On first run (task 0), create instance list natively on host
if [ $SLURM_ARRAY_TASK_ID -eq 0 ] && [ ! -f "$INSTANCE_LIST_FILE" ]; then
    mkdir -p $(dirname $INSTANCE_LIST_FILE)
    
    # Run instance list creation directly on host
    cd $OPENHANDS_ROOT
    python evaluation/benchmarks/swe_bench/scripts/slurm/create_instance_list.py \
         --dataset "$DATASET" \
         --split "$SPLIT" \
         --output "${INSTANCE_LIST_FILE}"
    cd $WORK_DIR
fi

# Wait for instance list to be created
max_wait=300  # 5 minutes
waited=0
while [ ! -f "$INSTANCE_LIST_FILE" ] && [ $waited -lt $max_wait ]; do
    sleep 5
    waited=$((waited + 5))
done

if [ ! -f "$INSTANCE_LIST_FILE" ]; then
    echo "Error: Instance list file not found after waiting"
    exit 1
fi

# Get the specific instance for this array task (run on host)
INSTANCE_ID=$(python -c "
import json
with open('$INSTANCE_LIST_FILE', 'r') as f:
    instances = json.load(f)
    if $SLURM_ARRAY_TASK_ID < len(instances):
        print(instances[$SLURM_ARRAY_TASK_ID])
")

if [ -z "$INSTANCE_ID" ]; then
    echo "No instance for task $SLURM_ARRAY_TASK_ID"
    exit 0
fi

echo "Processing instance: $INSTANCE_ID (task $SLURM_ARRAY_TASK_ID)"

# Get the instance-specific Docker image
INSTANCE_IMAGE=$(cd $OPENHANDS_ROOT && python -c "
import sys
sys.path.append('.')
from evaluation.benchmarks.swe_bench.run_infer import get_instance_docker_image
print(get_instance_docker_image('$INSTANCE_ID'))
")

echo "Using instance image: $INSTANCE_IMAGE"

# Run the evaluation in the instance-specific pyxis container
srun --container-image="$INSTANCE_IMAGE" \
     --container-mounts="$OPENHANDS_ROOT:/workspace,$WORK_DIR/evaluation_outputs:/workspace/evaluation_outputs" \
     --container-workdir="/workspace" \
     --container-env="INSTANCE_ID=$INSTANCE_ID,RUNTIME=local" \
     python evaluation/benchmarks/swe_bench/scripts/slurm/run_single_instance.py \
         --instance-id "$INSTANCE_ID" \
         --agent-cls "$AGENT" \
         --llm-config "$MODEL_CONFIG" \
         --max-iterations "$MAX_ITER" \
         --dataset "$DATASET" \
         --split "$SPLIT" \
         --mode "$MODE" \
         --output-dir "$EVAL_OUTPUT_DIR" \
         --task-id "$SLURM_ARRAY_TASK_ID" \
         --runtime local