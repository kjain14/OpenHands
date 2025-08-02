#!/bin/bash
# SWE-Bench end-to-end evaluation script for SLURM with Pyxis
# This script runs natively on the host but uses Pyxis containers for each instance
# SBATCH directives are handled dynamically by the launcher script

# Parse command line arguments
MODEL_CONFIG=$1
AGENT=$2
DATASET=$3
SPLIT=$4
MODE=${5:-swe}
MAX_ITER=${6:-100}
EVAL_ENVIRONMENT=${7:-local}  # local or modal

if [ -z "$MODEL_CONFIG" ] || [ -z "$AGENT" ] || [ -z "$DATASET" ] || [ -z "$SPLIT" ]; then
    echo "Usage: $0 MODEL_CONFIG AGENT DATASET SPLIT [MODE] [MAX_ITER] [EVAL_ENVIRONMENT]"
    echo "Example: $0 llm-config.json CodeActAgent princeton-nlp/SWE-bench_Lite test"
    exit 1
fi

# Set up paths
export OPENHANDS_ROOT=$(realpath $(dirname $0)/../../../../../)
export WORK_DIR=$PWD

# Create log directories
mkdir -p slurm_logs
mkdir -p evaluation_outputs/swe_bench_e2e_pyxis

# Export environment variables for the container
export EVAL_OUTPUT_DIR="/workspace/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}"

# Get instance ID for this array task
INSTANCE_LIST_FILE="${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}/instance_list.json"

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

# =============================================================================
# PHASE 1: INFERENCE - Run agent to generate solution
# =============================================================================
echo "=========================================="
echo "PHASE 1: Running inference for instance $INSTANCE_ID"
echo "=========================================="

# Run the inference in the instance-specific pyxis container
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

# Check if inference succeeded
INFERENCE_OUTPUT_FILE="${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}/output_task_${SLURM_ARRAY_TASK_ID}.jsonl"
if [ ! -f "$INFERENCE_OUTPUT_FILE" ]; then
    echo "Error: Inference failed - output file not found: $INFERENCE_OUTPUT_FILE"
    exit 1
fi

echo "Inference completed successfully for instance $INSTANCE_ID"

# =============================================================================
# PHASE 2: EVALUATION - Apply patches and run tests
# =============================================================================
echo "=========================================="
echo "PHASE 2: Running evaluation for instance $INSTANCE_ID"
echo "=========================================="

# Only run evaluation on the final task to avoid conflicts
# We'll evaluate all instances together after all inference is complete
if [ $SLURM_ARRAY_TASK_ID -eq $((SLURM_ARRAY_SIZE - 1)) ]; then
    echo "Final task - waiting for all inference to complete and then running evaluation"
    
    # Wait for all output files to be created
    echo "Waiting for all inference tasks to complete..."
    max_wait_eval=3600  # 1 hour
    waited_eval=0
    all_complete=false
    
    while [ $waited_eval -lt $max_wait_eval ] && [ "$all_complete" = false ]; do
        missing_count=0
        for i in $(seq 0 $((SLURM_ARRAY_SIZE - 1))); do
            output_file="${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}/output_task_${i}.jsonl"
            if [ ! -f "$output_file" ]; then
                missing_count=$((missing_count + 1))
            fi
        done
        
        if [ $missing_count -eq 0 ]; then
            all_complete=true
            echo "All inference tasks completed!"
        else
            echo "Still waiting for $missing_count tasks to complete..."
            sleep 30
            waited_eval=$((waited_eval + 30))
        fi
    done
    
    if [ "$all_complete" = false ]; then
        echo "Warning: Not all inference tasks completed within timeout. Proceeding with evaluation of available results."
    fi
    
    # Aggregate all inference outputs into a single file
    AGGREGATED_OUTPUT="${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}/aggregated_output.jsonl"
    echo "Aggregating inference outputs to $AGGREGATED_OUTPUT"
    
    # Combine all output files
    cat "${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}"/output_task_*.jsonl > "$AGGREGATED_OUTPUT"
    
    echo "Running SWE-bench evaluation on aggregated results..."
    
    # Run evaluation directly on the host
    cd $OPENHANDS_ROOT
    
    # Install swebench if not available
    pip install swebench || echo 'swebench already installed or installation failed'
    
    # Convert to SWE-bench format if needed
    python evaluation/benchmarks/swe_bench/scripts/eval/convert_oh_output_to_swe_json.py "$AGGREGATED_OUTPUT"
    
    # Get the converted file path
    SWEBENCH_FORMAT_FILE="${AGGREGATED_OUTPUT%.jsonl}.swebench.jsonl"
    
    if [ ! -f "$SWEBENCH_FORMAT_FILE" ]; then
        echo 'Error: SWE-bench format conversion failed'
        exit 1
    fi
    
    # Run SWE-bench evaluation
    RUN_ID=$(date +"%Y%m%d_%H%M%S")
    MODAL_FLAG=""
    if [ "$EVAL_ENVIRONMENT" = "modal" ]; then
        MODAL_FLAG="--modal true"
    fi
    
    python -m swebench.harness.run_evaluation \
        --dataset_name "$DATASET" \
        --split "$SPLIT" \
        --predictions_path "$SWEBENCH_FORMAT_FILE" \
        --timeout 3600 \
        --cache_level instance \
        --max_workers 4 \
        --run_id "$RUN_ID" \
        $MODAL_FLAG
    
    # Move results to output directory
    MODEL_NAME_OR_PATH=$(jq -r '.model_name_or_path' "$SWEBENCH_FORMAT_FILE" | head -n 1)
    RESULT_OUTPUT_DIR="${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}"
    
    if [ -d "logs/run_evaluation/$RUN_ID/$MODEL_NAME_OR_PATH" ]; then
        mv "logs/run_evaluation/$RUN_ID/$MODEL_NAME_OR_PATH" "$RESULT_OUTPUT_DIR/eval_outputs"
        echo "$RUN_ID" > "$RESULT_OUTPUT_DIR/run_id.txt"
    fi
    
    # Move report file if it exists
    if [ -f "$MODEL_NAME_OR_PATH.$RUN_ID.json" ]; then
        mv "$MODEL_NAME_OR_PATH.$RUN_ID.json" "$RESULT_OUTPUT_DIR/report.json"
    fi
    
    echo 'Evaluation completed successfully!'
    cd $WORK_DIR
    
    echo "End-to-end evaluation completed for job ${SLURM_ARRAY_JOB_ID}"
    echo "Results available at: ${WORK_DIR}/evaluation_outputs/swe_bench_e2e_pyxis/job_${SLURM_ARRAY_JOB_ID}/"
else
    echo "Inference task $SLURM_ARRAY_TASK_ID completed. Evaluation will be run by the final task."
fi