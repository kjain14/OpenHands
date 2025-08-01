#!/usr/bin/env python3
"""
Create a list of instance IDs from a SWE-Bench dataset for SLURM array processing.
"""

import argparse
import json
import os
import sys

# Add parent directories to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from datasets import load_dataset
import pandas as pd

from evaluation.benchmarks.swe_bench.run_infer import filter_dataset, set_dataset_type


def main():
    parser = argparse.ArgumentParser(description='Create instance list for SLURM array processing')
    parser.add_argument('--dataset', type=str, required=True, help='Dataset name')
    parser.add_argument('--split', type=str, required=True, help='Dataset split')
    parser.add_argument('--output', type=str, required=True, help='Output JSON file path')
    parser.add_argument('--filter-verified', action='store_true', help='Filter for SWE-Gym verified instances')
    
    args = parser.parse_args()
    
    # Load dataset
    print(f"Loading dataset {args.dataset} with split {args.split}...")
    dataset = load_dataset(args.dataset, split=args.split)
    
    # Set dataset type
    set_dataset_type(args.dataset)
    
    # Convert to pandas and filter
    df = dataset.to_pandas()
    filtered_df = filter_dataset(df, 'instance_id')
    
    # Additional filtering for SWE-Gym if needed
    if args.filter_verified and 'swe-gym' in args.dataset.lower():
        verified_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../split/swegym_verified_instances.json'
        )
        if os.path.exists(verified_file):
            with open(verified_file, 'r') as f:
                verified_instances = json.load(f)
                filtered_df = filtered_df[filtered_df['instance_id'].isin(verified_instances)]
                print(f"Filtered to {len(filtered_df)} verified instances")
    
    # Get instance IDs
    instance_ids = filtered_df['instance_id'].tolist()
    print(f"Found {len(instance_ids)} instances")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Write to output file
    with open(args.output, 'w') as f:
        json.dump(instance_ids, f, indent=2)
    
    print(f"Instance list written to {args.output}")


if __name__ == '__main__':
    main()