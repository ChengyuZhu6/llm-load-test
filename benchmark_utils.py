import csv
import os
import json
import numpy as np
import pandas as pd
import re
import subprocess

def replace_string_in_file(file_path, old_string, new_string):
    # Read in the file
    with open(file_path, 'r') as file:
        filedata = file.read()

    # Replace the target string
    new_filedata = re.sub(old_string, new_string, filedata)

    # Write the file out again
    with open(file_path, 'w') as file:
        file.write(new_filedata)
        
def command_execute(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    print(result)

def extract_values(filename):
    # Define the regex pattern
    pattern = r"output_tokens(\d+)-batch(\d+)-pod(\d+)\.json"
    
    # Search for the pattern in the filename
    match = re.search(pattern, filename)
    
    # If a match is found, extract the groups
    if match:
        output_tokens = match.group(1)
        batch_size = match.group(2)
        pod_num = match.group(3)
        return output_tokens, batch_size, pod_num
    else:
        return None

def generate_csv(output_dir, csv_file_name):
    """Generate a CSV file from results."""
    print("*Generating CSV output...")
    columns = [ "batch_size", "pod_num",
        "tpot_min", "tpot_max", "tpot_median", "tpot_mean", "tpot_percentile_80", "tpot_percentile_90", "tpot_percentile_95", "tpot_percentile_99",
        "ttft_min", "ttft_max", "ttft_median", "ttft_mean", "ttft_percentile_80", "ttft_percentile_90", "ttft_percentile_95", "ttft_percentile_99",
        "itl_min", "itl_max", "itl_median", "itl_mean", "itl_percentile_80", "itl_percentile_90", "itl_percentile_95", "itl_percentile_99",
        "tt_ack_min", "tt_ack_max", "tt_ack_median", "tt_ack_mean", "tt_ack_percentile_80", "tt_ack_percentile_90", "tt_ack_percentile_95", "tt_ack_percentile_99",
        "response_time_min", "response_time_max", "response_time_median", "response_time_mean", "response_time_percentile_80", "response_time_percentile_90", "response_time_percentile_95", "response_time_percentile_99",
        "output_tokens_min", "output_tokens_max", "output_tokens_median", "output_tokens_mean", "output_tokens_percentile_80", "output_tokens_percentile_90", "output_tokens_percentile_95", "output_tokens_percentile_99",
        "output_tokens_before_timeout_min", "output_tokens_before_timeout_max", "output_tokens_before_timeout_median", "output_tokens_before_timeout_mean", "output_tokens_before_timeout_percentile_80", "output_tokens_before_timeout_percentile_90", "output_tokens_before_timeout_percentile_95", "output_tokens_before_timeout_percentile_99",
        "input_tokens_min", "input_tokens_max", "input_tokens_median", "input_tokens_mean", "input_tokens_percentile_80", "input_tokens_percentile_90", "input_tokens_percentile_95", "input_tokens_percentile_99",
        "throughput_full_duration", "full_duration", "throughput", "total_requests", "req_completed_within_test_duration", "total_failures", "failure_rate"
    ]
    files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f)) and f != csv_file_name]
    with open(output_dir + csv_file_name, mode='w') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        for f in files:
            _, batch_size, pod_num = extract_values(f)
            with open(output_dir + f, mode='r') as output_data_file:
                data = json.load(output_data_file)
                summary = data['summary']
                
                # Extract each metric from the JSON
                row = {}
                row["batch_size"] = batch_size
                row["pod_num"] = pod_num
                for metric in summary:
                    if isinstance(summary[metric], dict):
                        for key in summary[metric]:
                            row[f"{metric}_{key}"] = summary[metric][key]
                    else:
                        row[metric] = summary[metric]

                writer.writerow(row)