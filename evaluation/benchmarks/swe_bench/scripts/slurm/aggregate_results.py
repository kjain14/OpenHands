#!/usr/bin/env python3
"""
Aggregate SLURM array job results into a single output file.
"""

import argparse
import json
import os
import glob
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Aggregate SLURM array job results')
    parser.add_argument('--input-dir', type=str, required=True, help='Directory containing SLURM job outputs')
    parser.add_argument('--output-file', type=str, required=True, help='Combined output JSONL file')
    parser.add_argument('--job-id', type=str, help='Specific SLURM job ID to aggregate (optional)')
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: Input directory {input_dir} does not exist")
        return 1
    
    # Find all output files
    if args.job_id:
        pattern = f"job_{args.job_id}/output_task_*.jsonl"
    else:
        pattern = "*/output_task_*.jsonl"
    
    output_files = list(input_dir.glob(pattern))
    
    if not output_files:
        print(f"No output files found with pattern: {pattern}")
        return 1
    
    print(f"Found {len(output_files)} output files")
    
    # Aggregate results
    all_results = []
    processed_instances = set()
    
    for output_file in sorted(output_files):
        print(f"Processing: {output_file}")
        
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    if line.strip():
                        result = json.loads(line)
                        instance_id = result.get('instance_id')
                        
                        if instance_id in processed_instances:
                            print(f"Warning: Duplicate instance {instance_id} found in {output_file}")
                            continue
                        
                        processed_instances.add(instance_id)
                        all_results.append(result)
                        
        except Exception as e:
            print(f"Error processing {output_file}: {e}")
            continue
    
    print(f"Aggregated {len(all_results)} unique results")
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    
    # Write aggregated results
    with open(args.output_file, 'w') as f:
        for result in all_results:
            f.write(json.dumps(result) + '\n')
    
    print(f"Results written to: {args.output_file}")
    
    # Also check for error files
    if args.job_id:
        error_pattern = f"job_{args.job_id}/error_task_*.jsonl"
    else:
        error_pattern = "*/error_task_*.jsonl"
    
    error_files = list(input_dir.glob(error_pattern))
    if error_files:
        print(f"\nFound {len(error_files)} error files:")
        error_output_file = args.output_file.replace('.jsonl', '_errors.jsonl')
        
        all_errors = []
        for error_file in error_files:
            try:
                with open(error_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            all_errors.append(json.loads(line))
            except Exception as e:
                print(f"Error processing {error_file}: {e}")
        
        if all_errors:
            with open(error_output_file, 'w') as f:
                for error in all_errors:
                    f.write(json.dumps(error) + '\n')
            print(f"Errors written to: {error_output_file}")
    
    return 0


if __name__ == '__main__':
    exit(main())