# SWE-Bench SLURM Integration with Pyxis

This directory contains scripts for running complete SWE-Bench evaluations on SLURM clusters using Pyxis containers with local runtime.

## Overview

The SLURM integration provides:
- **End-to-end SWE-bench evaluation**: Inference + test execution + metrics
- **Pyxis containerized execution**: Using local runtime instead of Docker-in-Docker
- **Dynamic SLURM job generation**: Flexible resource allocation
- **SLURM job arrays**: Parallel instance processing with automatic coordination
- **Automatic result aggregation**: Complete pipeline from agent runs to final metrics

## Files

- `launch_swe_bench.sh` - Main launcher script with dynamic SBATCH generation
- `run_swe_bench_pyxis.sh` - SLURM execution script for inference-only mode
- `run_swe_bench_end_to_end_pyxis.sh` - SLURM execution script for complete pipeline
- `run_single_instance.py` - Python script to process a single SWE-Bench instance
- `create_instance_list.py` - Creates instance list for array job distribution
- `aggregate_results.py` - Aggregates results from SLURM array jobs

## Quick Start

### End-to-End Evaluation (Recommended)

Run complete SWE-bench pipeline: inference → patch application → test execution → metrics

```bash
# Navigate to OpenHands root directory
cd /path/to/OpenHands

# Run complete SWE-Bench Lite evaluation
./evaluation/benchmarks/swe_bench/scripts/slurm/launch_swe_bench.sh \
    --end-to-end \
    llm-config.json \
    CodeActAgent \
    princeton-nlp/SWE-bench_Lite \
    test
```

### Inference-Only Mode

Run only the agent inference phase (requires manual evaluation afterward):

```bash
# Run inference only
./evaluation/benchmarks/swe_bench/scripts/slurm/launch_swe_bench.sh \
    llm-config.json \
    CodeActAgent \
    princeton-nlp/SWE-bench_Lite \
    test
```

### Advanced Configuration

```bash
# Custom configuration with GPU support and modal evaluation
./evaluation/benchmarks/swe_bench/scripts/slurm/launch_swe_bench.sh \
    --end-to-end \
    --eval-env modal \
    --container-image my-custom-image:latest \
    --mode swt \
    --max-iter 200 \
    --gpu \
    --max-parallel 20 \
    --time-limit 24:00:00 \
    --memory 64G \
    --cpus 8 \
    llm-config.json \
    CodeActAgent \
    princeton-nlp/SWE-bench \
    test
```

## Configuration Options

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `MODEL_CONFIG` | Path to LLM configuration file | Required |
| `AGENT` | Agent class name (e.g., CodeActAgent) | Required |
| `DATASET` | Dataset name | Required |
| `SPLIT` | Dataset split | Required |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--end-to-end` | Run complete pipeline: inference + evaluation | false (inference only) |
| `--eval-env ENV` | Evaluation environment: `local` or `modal` | local |
| `--container-image IMG` | Container image for Pyxis | ghcr.io/openhands/openhands:latest |
| `--mode MODE` | Evaluation mode (swe, swt, swt-ci) | swe |
| `--max-iter N` | Maximum iterations per instance | 100 |
| `--max-parallel N` | Maximum parallel jobs | 50 |
| `--time-limit TIME` | Time limit per job (HH:MM:SS) | 08:00:00 (inference), 12:00:00 (end-to-end) |
| `--memory MEM` | Memory per job | 32G |
| `--cpus N` | CPUs per job | 4 |
| `--gpu` | Request GPU resources | false |
| `--array-size N` | Override array size | Auto-detected |
| `--dry-run` | Generate and display SBATCH script without submitting | false |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `EVAL_NOTE` | Additional note for evaluation | None |
| `EVAL_CONDENSER` | Condenser configuration | None |
| `USE_HINT_TEXT` | Use hint text | false |
| `RUN_WITH_BROWSING` | Run with browsing | false |

## Workflow

### End-to-End Pipeline (Recommended)

1. **Job Submission**: Dynamic SBATCH script generated with user-specified resources
2. **Instance Distribution**: Each array task processes one SWE-Bench instance  
3. **Phase 1 - Inference**: All tasks run agent inference in parallel using local runtime
4. **Coordination**: Final task waits for all inference to complete
5. **Phase 2 - Evaluation**: Aggregates results and runs SWE-bench harness for test execution
6. **Final Output**: Complete metrics and results automatically generated

### Inference-Only Pipeline

1. **Job Submission**: Dynamic SBATCH script generated
2. **Parallel Inference**: Each task generates solution for one instance
3. **Manual Aggregation**: Use `aggregate_results.py` to combine results
4. **Manual Evaluation**: Run evaluation script separately

## Monitoring Jobs

### Check Job Status
```bash
# View job status
squeue -j JOB_ID

# View detailed job information
scontrol show job JOB_ID

# View specific array task
squeue -j JOB_ID_TASK_ID
```

### View Logs
```bash
# View output logs
ls slurm_logs/swe-bench-*JOB_ID_*.out

# View error logs
ls slurm_logs/swe-bench-*JOB_ID_*.err

# Follow a specific task log
tail -f slurm_logs/swe-bench-JOB_ID_TASK_ID.out
```

### Cancel Jobs
```bash
# Cancel entire job array
scancel JOB_ID

# Cancel specific array task
scancel JOB_ID_TASK_ID
```

## Results

### End-to-End Results

Results are automatically generated and available at:
```
evaluation_outputs/swe_bench_e2e_pyxis/job_JOB_ID/
├── report.json              # Final SWE-bench metrics
├── eval_outputs/           # Detailed test execution results  
├── aggregated_output.jsonl # Combined inference results
└── output_task_*.jsonl     # Individual task outputs

slurm_logs/
├── sbatch_TIMESTAMP_e2e.sh # Generated SBATCH script
├── job_JOB_ID_info.json    # Job metadata and configuration
└── swe-bench-e2e-pyxis-JOB_ID_*.{out,err}  # Job logs
```

### Inference-Only Results

For inference-only runs, manually aggregate and evaluate:

```bash
# Aggregate results for a specific job
python evaluation/benchmarks/swe_bench/scripts/slurm/aggregate_results.py \
    --input-dir evaluation_outputs/swe_bench_pyxis \
    --job-id JOB_ID \
    --output-file evaluation_outputs/swe_bench_job_JOB_ID.jsonl

# Run evaluation
bash evaluation/benchmarks/swe_bench/scripts/eval_infer.sh \
    evaluation_outputs/swe_bench_job_JOB_ID.jsonl \
    "" \
    princeton-nlp/SWE-bench_Lite \
    test \
    local
```

## Cluster Requirements

### SLURM Configuration
- SLURM cluster with job array support
- Python 3.8+ available on compute nodes
- Access to shared filesystem for result storage

### For Pyxis Support
- Pyxis plugin installed on SLURM cluster  
- Container registry access for pulling images
- Local runtime support (no Docker-in-Docker required)

### Resource Recommendations

| Dataset | Instances | Inference Resources | End-to-End Resources |
|---------|-----------|-------------------|-------------------|
| SWE-bench_Lite | ~300 | 4 CPUs, 32GB RAM, 8h | 4 CPUs, 32GB RAM, 12h |
| SWE-bench | ~2,294 | 4 CPUs, 32GB RAM, 8h | 4 CPUs, 32GB RAM, 12h |
| SWE-bench_Verified | ~500 | 4 CPUs, 32GB RAM, 8h | 4 CPUs, 32GB RAM, 12h |

## Troubleshooting

### Common Issues

1. **Job Array Size Mismatch**
   - Manually set `--array-size` if auto-detection fails
   - Check dataset accessibility from compute nodes

2. **Container Image Issues**
   - Ensure container registry is accessible from compute nodes
   - Verify image exists and has correct permissions

3. **Permission Errors**
   - Ensure scripts are executable: `chmod +x *.sh`
   - Check shared filesystem permissions

4. **Resource Constraints**
   - Increase time limit for complex instances
   - Adjust memory allocation based on dataset

### Dry Run Mode

Before submitting jobs, validate your configuration with dry run mode:

```bash
# Validate configuration without submitting
./evaluation/benchmarks/swe_bench/scripts/slurm/launch_swe_bench.sh \
    --dry-run \
    --end-to-end \
    llm-config.json \
    CodeActAgent \
    princeton-nlp/SWE-bench_Lite \
    test
```

This will:
- Generate the complete SBATCH script
- Display the script content for review
- Show the exact submission command
- Save the script to `slurm_logs/sbatch_TIMESTAMP_[e2e|inf].sh`

### Debug Mode

For debugging, run a single instance manually:

```bash
# Test single instance
python evaluation/benchmarks/swe_bench/scripts/slurm/run_single_instance.py \
    --instance-id "django__django-12125" \
    --agent-cls CodeActAgent \
    --llm-config llm-config.json \
    --max-iterations 100 \
    --dataset princeton-nlp/SWE-bench_Lite \
    --split test \
    --mode swe \
    --output-dir debug_output \
    --task-id 0 \
    --runtime local
```

## Testing the Pipeline with One Instance

Before running a full evaluation, it's recommended to test the pipeline with a single instance to verify your configuration and setup. This helps identify issues early and saves computational resources.

### Quick Test with Single Instance

To test the complete end-to-end pipeline with one instance:

```bash
# First, do a dry run to validate configuration
./evaluation/benchmarks/swe_bench/scripts/slurm/launch_swe_bench.sh \
    --dry-run \
    --end-to-end \
    --array-size 1 \
    --max-parallel 1 \
    --time-limit 02:00:00 \
    llm-config.json \
    CodeActAgent \
    princeton-nlp/SWE-bench_Lite \
    test

# Then submit the actual job
./evaluation/benchmarks/swe_bench/scripts/slurm/launch_swe_bench.sh \
    --end-to-end \
    --array-size 1 \
    --max-parallel 1 \
    --time-limit 02:00:00 \
    llm-config.json \
    CodeActAgent \
    princeton-nlp/SWE-bench_Lite \
    test
```

### Manual Single Instance Testing

For more control and detailed debugging:

```bash
# 1. First, identify a specific instance to test
python -c "
from datasets import load_dataset
ds = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
print(f'First instance: {ds[0][\"instance_id\"]}')
"

# 2. Run that specific instance
python evaluation/benchmarks/swe_bench/scripts/slurm/run_single_instance.py \
    --instance-id "django__django-12125" \
    --agent-cls CodeActAgent \
    --llm-config llm-config.json \
    --max-iterations 100 \
    --dataset princeton-nlp/SWE-bench_Lite \
    --split test \
    --mode swe \
    --output-dir test_single_output \
    --task-id 0 \
    --runtime local

# 3. Check the output
ls test_single_output/
cat test_single_output/output_task_0.jsonl
```

### Validating Your Test Results

After running a single instance:

1. **Check the output file exists**: `test_single_output/output_task_0.jsonl`
2. **Verify the solution**: The JSONL should contain a solution with a patch
3. **Review logs**: Check for any errors or warnings in the output
4. **Test evaluation**: Run a quick evaluation on the single result

```bash
# Quick evaluation test
bash evaluation/benchmarks/swe_bench/scripts/eval_infer.sh \
    test_single_output/output_task_0.jsonl \
    "" \
    princeton-nlp/SWE-bench_Lite \
    test \
    local
```

### Common Single Instance Issues

- **Configuration errors**: Wrong LLM config or agent class name
- **Dataset access**: Issues loading the dataset from HuggingFace
- **Resource limits**: Insufficient memory or time for complex instances
- **Environment setup**: Missing dependencies or incorrect paths

Once your single instance test passes successfully, you can confidently scale up to the full dataset.

## Performance Optimization

### Parallel Jobs
- Adjust `--max-parallel` based on cluster capacity
- Monitor cluster utilization to avoid overloading

### Resource Allocation
- Use `--gpu` only if models require GPU acceleration
- Increase memory for large repositories or long contexts

### Container Optimization
- Use pre-built images with dependencies installed
- Consider using cluster-local container registry
- Local runtime eliminates Docker-in-Docker overhead

## Integration with Existing Workflows

The SLURM integration is designed to be compatible with existing SWE-Bench evaluation workflows:

- Uses the same configuration files and formats
- Maintains compatibility with existing evaluation scripts
- Results can be processed with standard SWE-Bench tools

## Support

For issues specific to SLURM integration, check:
1. SLURM cluster documentation
2. Pyxis documentation (if using containers)
3. OpenHands SWE-Bench documentation

Common cluster-specific configurations may need adjustment in the SLURM scripts based on your environment.