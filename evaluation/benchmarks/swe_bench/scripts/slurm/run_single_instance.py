#!/usr/bin/env python3
"""Run SWE-Bench evaluation for a single instance.
This script is designed to be called from SLURM array jobs.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    )
)

from datasets import load_dataset

from evaluation.benchmarks.swe_bench.run_infer import (
    process_instance,
    set_dataset_type,
)
from evaluation.utils.shared import (
    make_metadata,
)
from openhands.core.config import (
    get_llm_config_arg,
)
from openhands.core.config.condenser_config import NoOpCondenserConfig
from openhands.core.config.utils import get_condenser_config_arg
from openhands.core.logger import openhands_logger as logger


def main():
    parser = argparse.ArgumentParser(
        description="Run SWE-Bench evaluation for a single instance"
    )
    parser.add_argument(
        "--instance-id", type=str, required=True, help="Instance ID to process"
    )
    parser.add_argument("--agent-cls", type=str, required=True, help="Agent class name")
    parser.add_argument(
        "--llm-config", type=str, required=True, help="LLM configuration file"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=100, help="Maximum iterations"
    )
    parser.add_argument("--dataset", type=str, required=True, help="Dataset name")
    parser.add_argument("--split", type=str, required=True, help="Dataset split")
    parser.add_argument(
        "--mode", type=str, default="swe", choices=["swe", "swt", "swt-ci"]
    )
    parser.add_argument(
        "--output-dir", type=str, required=True, help="Output directory"
    )
    parser.add_argument(
        "--task-id", type=int, required=True, help="SLURM array task ID"
    )
    parser.add_argument(
        "--runtime",
        type=str,
        default="docker",
        choices=["docker", "local"],
        help="Runtime to use for evaluation",
    )

    args = parser.parse_args()

    # Set runtime environment variable if specified
    if args.runtime:
        os.environ["RUNTIME"] = args.runtime

    # Load dataset
    logger.info(f"Loading dataset {args.dataset} with split {args.split}...")
    dataset = load_dataset(args.dataset, split=args.split)
    set_dataset_type(args.dataset)

    # Convert to pandas and filter for the specific instance
    df = dataset.to_pandas()
    instance_df = df[df["instance_id"] == args.instance_id]

    if len(instance_df) == 0:
        logger.error(f"Instance {args.instance_id} not found in dataset")
        sys.exit(1)

    instance = instance_df.iloc[0]
    logger.info(f"Processing instance: {args.instance_id}")

    # Set up LLM config
    llm_config = get_llm_config_arg(args.llm_config)
    if llm_config is None:
        raise ValueError(f"Could not find LLM config: {args.llm_config}")

    llm_config.log_completions = True
    llm_config.modify_params = False

    # Get condenser config
    condenser_name = os.environ.get("EVAL_CONDENSER")
    if condenser_name:
        condenser_config = get_condenser_config_arg(condenser_name)
        if condenser_config is None:
            raise ValueError(
                f"Could not find Condenser config: EVAL_CONDENSER={condenser_name}"
            )
    else:
        condenser_config = NoOpCondenserConfig()

    # Create metadata
    details = {"mode": args.mode}
    dataset_description = (
        args.dataset.replace("/", "__") + "-" + args.split.replace("/", "__")
    )

    # Create eval note with task ID to ensure unique output files
    eval_note = f"slurm-task-{args.task_id}"
    if os.environ.get("EVAL_NOTE"):
        eval_note = f"{os.environ.get('EVAL_NOTE')}-{eval_note}"

    metadata = make_metadata(
        llm_config,
        dataset_description,
        args.agent_cls,
        args.max_iterations,
        eval_note,
        args.output_dir,
        details=details,
        condenser_config=condenser_config,
    )

    # Process the instance
    logger.info(f"Starting evaluation for instance {args.instance_id}")

    try:
        # Run the evaluation
        output = asyncio.run(process_instance(instance, metadata, reset_logger=False))

        # Save the output
        output_file = os.path.join(args.output_dir, f"output_task_{args.task_id}.jsonl")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "a") as f:
            f.write(json.dumps(output.model_dump()) + "\n")

        logger.info(f"Successfully processed instance {args.instance_id}")
        logger.info(f"Output saved to {output_file}")

    except Exception as e:
        logger.error(f"Error processing instance {args.instance_id}: {str(e)}")
        import traceback

        traceback.print_exc()

        # Save error output
        error_output = {
            "instance_id": args.instance_id,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "metadata": metadata.model_dump() if metadata else None,
        }

        error_file = os.path.join(args.output_dir, f"error_task_{args.task_id}.jsonl")
        with open(error_file, "a") as f:
            f.write(json.dumps(error_output) + "\n")

        sys.exit(1)


if __name__ == "__main__":
    main()
