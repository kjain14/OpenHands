#!/bin/bash
# Main launcher script for SWE-Bench evaluation on SLURM with pyxis

set -e

# Default values
CONTAINER_IMAGE="ghcr.io/openhands/openhands:latest"
END_TO_END=false
EVAL_ENVIRONMENT="local"
MAX_PARALLEL=50
TIME_LIMIT="08:00:00"
MEMORY="32G"
CPUS=4
USE_GPU=false
ARRAY_SIZE=""
DRY_RUN=false

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] MODEL_CONFIG AGENT DATASET SPLIT

Launch SWE-Bench evaluation on SLURM cluster

Arguments:
    MODEL_CONFIG    Path to LLM configuration file
    AGENT           Agent class name (e.g., CodeActAgent)
    DATASET         Dataset name (e.g., princeton-nlp/SWE-bench_Lite)
    SPLIT           Dataset split (e.g., test)

Options:
    --container-image IMG   Container image to use (default: ghcr.io/openhands/openhands:latest)
    --end-to-end            Run complete pipeline: inference + evaluation (default: inference only)
    --eval-env ENV          Evaluation environment: local or modal (default: local)
    --mode MODE             Evaluation mode (default: swe)
    --max-iter N            Maximum iterations (default: 100)
    --max-parallel N        Maximum parallel jobs (default: 50)
    --time-limit TIME       Time limit per job (default: 08:00:00 for inference, 12:00:00 for end-to-end)
    --memory MEM            Memory per job (default: 32G)
    --cpus N                CPUs per job (default: 4)
    --gpu                   Request GPU resources
    --array-size N          Override array size (auto-detected if not specified)
    --dry-run               Generate and display SBATCH script without submitting
    --help                  Show this help message

Environment Variables:
    EVAL_NOTE              Additional note for evaluation
    EVAL_CONDENSER         Condenser configuration
    USE_HINT_TEXT          Use hint text (default: false)
    RUN_WITH_BROWSING      Run with browsing (default: false)

Examples:
    # Basic usage
    $0 llm-config.json CodeActAgent princeton-nlp/SWE-bench_Lite test

    # With custom container image
    $0 --container-image my-custom-image:latest llm-config.json CodeActAgent princeton-nlp/SWE-bench_Lite test

    # With custom parameters
    $0 --mode swt --max-iter 200 --gpu --max-parallel 20 llm-config.json CodeActAgent princeton-nlp/SWE-bench test

    # End-to-end evaluation (inference + test execution)
    $0 --end-to-end llm-config.json CodeActAgent princeton-nlp/SWE-bench_Lite test
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --container-image)
            CONTAINER_IMAGE="$2"
            shift 2
            ;;
        --end-to-end)
            END_TO_END=true
            shift
            ;;
        --eval-env)
            EVAL_ENVIRONMENT="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --max-iter)
            MAX_ITER="$2"
            shift 2
            ;;
        --max-parallel)
            MAX_PARALLEL="$2"
            shift 2
            ;;
        --time-limit)
            TIME_LIMIT="$2"
            shift 2
            ;;
        --memory)
            MEMORY="$2"
            shift 2
            ;;
        --cpus)
            CPUS="$2"
            shift 2
            ;;
        --gpu)
            USE_GPU=true
            shift
            ;;
        --array-size)
            ARRAY_SIZE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

# Check required arguments
if [ $# -lt 4 ]; then
    echo "Error: Missing required arguments"
    usage
    exit 1
fi

MODEL_CONFIG="$1"
AGENT="$2"
DATASET="$3"
SPLIT="$4"
MODE="${MODE:-swe}"
MAX_ITER="${MAX_ITER:-100}"

# Validate required files exist
if [ ! -f "$MODEL_CONFIG" ]; then
    echo "Error: Model config file not found: $MODEL_CONFIG"
    exit 1
fi

# Get absolute path to OpenHands root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENHANDS_ROOT="$(cd "$SCRIPT_DIR/../../../../../" && pwd)"

echo "OpenHands root: $OPENHANDS_ROOT"
echo "Model config: $MODEL_CONFIG"
echo "Agent: $AGENT"
echo "Dataset: $DATASET"
echo "Split: $SPLIT"
echo "Mode: $MODE"
echo "Max iterations: $MAX_ITER"
echo "Container image: $CONTAINER_IMAGE"
echo "End-to-end: $END_TO_END"
if [ "$END_TO_END" = true ]; then
    echo "Evaluation environment: $EVAL_ENVIRONMENT"
fi

# Create output directories
mkdir -p slurm_logs
mkdir -p evaluation_outputs

# Determine array size if not specified
if [ -z "$ARRAY_SIZE" ]; then
    echo "Determining dataset size..."
    cd "$OPENHANDS_ROOT"
    ARRAY_SIZE=$(python -c "
from datasets import load_dataset
import pandas as pd
from evaluation.benchmarks.swe_bench.run_infer import filter_dataset
try:
    dataset = load_dataset('$DATASET', split='$SPLIT')
    df = filter_dataset(dataset.to_pandas(), 'instance_id')
    print(len(df))
except Exception as e:
    print('Error:', e, file=sys.stderr)
    print('300')  # fallback
")
fi

# Adjust array size to be 0-indexed
ARRAY_END=$((ARRAY_SIZE - 1))
echo "Array size: 0-$ARRAY_END (total: $ARRAY_SIZE instances)"

# Adjust time limit for end-to-end runs
if [ "$END_TO_END" = true ] && [ "$TIME_LIMIT" = "08:00:00" ]; then
    TIME_LIMIT="12:00:00"
fi

# SBATCH arguments are now handled dynamically in the generated script

# Choose the appropriate SLURM script
if [ "$END_TO_END" = true ]; then
    SLURM_SCRIPT="$SCRIPT_DIR/run_swe_bench_end_to_end_pyxis.sh"
    SCRIPT_ARGS="$MODEL_CONFIG $AGENT $DATASET $SPLIT $MODE $MAX_ITER $CONTAINER_IMAGE $EVAL_ENVIRONMENT"
else
    SLURM_SCRIPT="$SCRIPT_DIR/run_swe_bench_pyxis.sh"
    SCRIPT_ARGS="$MODEL_CONFIG $AGENT $DATASET $SPLIT $MODE $MAX_ITER $CONTAINER_IMAGE"
fi

echo "Submitting SLURM job..."
echo "Script: $SLURM_SCRIPT"
echo "Args: $SCRIPT_ARGS"
echo "Time limit: $TIME_LIMIT"
echo "Resources: ${CPUS} CPUs, ${MEMORY} memory$([ "$USE_GPU" = true ] && echo ", 1 GPU" || echo "")"

# Create dynamic SBATCH script
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SBATCH_FILENAME="slurm_logs/sbatch_${TIMESTAMP}_$([ "$END_TO_END" = true ] && echo "e2e" || echo "inf").sh"
mkdir -p "$(dirname "$SBATCH_FILENAME")"

# Use saved filename instead of temporary file
TEMP_SBATCH_SCRIPT="$SBATCH_FILENAME"
cat > "$TEMP_SBATCH_SCRIPT" << EOF
#!/bin/bash
#SBATCH --job-name=swe-bench-$([ "$END_TO_END" = true ] && echo "e2e" || echo "inf")-pyxis
#SBATCH --output=slurm_logs/swe-bench-$([ "$END_TO_END" = true ] && echo "e2e" || echo "inf")-pyxis-%A_%a.out
#SBATCH --error=slurm_logs/swe-bench-$([ "$END_TO_END" = true ] && echo "e2e" || echo "inf")-pyxis-%A_%a.err
#SBATCH --time=$TIME_LIMIT
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=$CPUS
#SBATCH --mem=$MEMORY
#SBATCH --constraint=cpu
#SBATCH --array=0-$ARRAY_END%$MAX_PARALLEL
$([ "$USE_GPU" = true ] && echo "#SBATCH --gres=gpu:1")

# Source the actual execution script
exec "$SLURM_SCRIPT" $SCRIPT_ARGS
EOF

# Submit the job or show dry run
cd "$OPENHANDS_ROOT"

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "=== DRY RUN MODE - SBATCH script generated but not submitted ==="
    echo "SBATCH script saved to: $TEMP_SBATCH_SCRIPT"
    echo ""
    echo "=== Generated SBATCH script content ==="
    cat "$TEMP_SBATCH_SCRIPT"
    echo ""
    echo "=== To submit this job, run ==="
    echo "cd $OPENHANDS_ROOT && sbatch $TEMP_SBATCH_SCRIPT"
    echo ""
    exit 0
fi

JOB_ID=$(sbatch "$TEMP_SBATCH_SCRIPT" | grep -o '[0-9]*')

echo "Job submitted with ID: $JOB_ID"
echo "SBATCH script saved to: $TEMP_SBATCH_SCRIPT"

# Create a job info file
JOB_INFO_FILE="slurm_logs/job_${JOB_ID}_info.json"
cat > "$JOB_INFO_FILE" << EOF
{
    "job_id": "$JOB_ID",
    "model_config": "$MODEL_CONFIG",
    "agent": "$AGENT",
    "dataset": "$DATASET",
    "split": "$SPLIT",
    "mode": "$MODE",
    "max_iterations": $MAX_ITER,
    "use_pyxis": true,
    "end_to_end": $END_TO_END,
    "eval_environment": "$EVAL_ENVIRONMENT",
    "container_image": "$CONTAINER_IMAGE",
    "array_size": $ARRAY_SIZE,
    "max_parallel": $MAX_PARALLEL,
    "submitted_at": "$(date -Iseconds)",
    "eval_note": "${EVAL_NOTE:-}",
    "eval_condenser": "${EVAL_CONDENSER:-}",
    "sbatch_script": "$TEMP_SBATCH_SCRIPT"
}
EOF

echo "Job info saved to: $JOB_INFO_FILE"

# Print monitoring commands
echo ""
echo "Monitoring commands:"
echo "  View job status:    squeue -j $JOB_ID"
echo "  View job details:   scontrol show job $JOB_ID"
echo "  Cancel job:         scancel $JOB_ID"
echo "  View log files:     ls slurm_logs/swe-bench-*${JOB_ID}_*.{out,err}"
echo ""
if [ "$END_TO_END" = true ]; then
    echo "End-to-end evaluation will be automatically completed."
    echo "Final results will be available at:"
    echo "  evaluation_outputs/swe_bench_e2e_pyxis/job_${JOB_ID}/report.json"
else
    echo "After completion, aggregate results with:"
    echo "  python $SCRIPT_DIR/aggregate_results.py \\"
    echo "    --input-dir evaluation_outputs/swe_bench_pyxis \\"
    echo "    --job-id $JOB_ID \\"
    echo "    --output-file evaluation_outputs/swe_bench_job_${JOB_ID}.jsonl"
    echo ""
    echo "Then run evaluation with:"
    echo "  bash evaluation/benchmarks/swe_bench/scripts/eval_infer.sh \\"
    echo "    evaluation_outputs/swe_bench_job_${JOB_ID}.jsonl \\"
    echo "    \"\" \"$DATASET\" \"$SPLIT\" \"$EVAL_ENVIRONMENT\""
fi
