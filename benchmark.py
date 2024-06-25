import os
import yaml
from pathlib import Path
import benchmark_utils
from kubernetes import client, config, watch
import time

script_path = os.path.realpath(__file__)
script_dir = os.path.dirname(script_path)

def yaml_load(file):
    """Load a yaml file."""
    if not Path(file).is_file():
        raise FileNotFoundError(file)
    with open(file, "r", encoding="utf-8") as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise RuntimeError(f"Could not parse {file}") from exc
        
def cleanup_environment(benchmark_config, api_instance, namespace):
    deploy_yaml = benchmark_config.get("inference_deploy_yaml_path")
    benchmark_utils.command_execute('kubectl delete -f ' + deploy_yaml)
    kill_pod_binary = benchmark_config.get("kill_pod_binary_path")
    benchmark_utils.command_execute('bash ' + kill_pod_binary)
    # List all pods in the specified namespace
    
    api_response = api_instance.list_namespaced_pod(namespace)
    while api_response.items:
        time.sleep(3)
        api_response = api_instance.list_namespaced_pod(namespace)
    print("Resources defined in the YAML file have been deleted.")
    
def configure_new_testcase(benchmark_config, batch_size, pod_num, output_token):
    print("Start configure_new_testcase.")
    # Change the benchmark config
    benchmark_config_path = benchmark_config.get("benchmark_config_path")
    # Load the YAML file
    duration_time = benchmark_config.get("duration")
    concurrency = batch_size * pod_num
    output_name = benchmark_config.get("output").get("name")
    output_format = benchmark_config.get("output").get("format")
    output_file_name = output_name + "-output_tokens" + str(output_token) + "-batch" + str(batch_size) + "-pod" + str(pod_num) + "." + output_format
    with open(benchmark_config_path) as benchmark_config_file:
        benchmark_config_data = yaml.safe_load(benchmark_config_file)
    benchmark_config_data['output']['file'] = output_file_name
    benchmark_config_data['load_options']['concurrency'] = concurrency
    benchmark_config_data['load_options']['duration'] = duration_time
    benchmark_config_data['dataset']['max_output_tokens'] = output_token if output_token != -1 else 128
    benchmark_config_data['plugin_options']['constant_output_tokens'] = output_token
    with open(benchmark_config_path, 'w') as file:
        yaml.safe_dump(benchmark_config_data, file)
    print("Finish configure_new_testcase.")

def deploy_llm(benchmark_config, api_instance, batch_size, pod_num, namespace):
    print("Start deploy_llm.")
    # Change the pod number in the deploy yaml file
    deploy_yaml = benchmark_config.get("inference_deploy_yaml_path")
    with open(deploy_yaml) as deploy_file:
        deploy_data = yaml.safe_load(deploy_file)
    deploy_data['spec']['predictor']['minReplicas'] = pod_num
    with open(deploy_yaml, 'w') as file:
        yaml.safe_dump(deploy_data, file)
    
    # Change the batch size in the llm config
    llm_config_file = benchmark_config.get("llm_config_path")
    benchmark_utils.replace_string_in_file(llm_config_file, r'"batchSize": \d+', '"batchSize": '+ str(batch_size))
    benchmark_utils.command_execute('kubectl apply -f ' + deploy_yaml)
    
    time.sleep(5)
    w = watch.Watch()
    
    for event in w.stream(api_instance.list_namespaced_pod, namespace=namespace):
        all_running = all(pod.status.phase == 'Running' for pod in api_instance.list_namespaced_pod(namespace=namespace).items)
        
        if all_running:
            print("All pods are running")
            w.stop()
            break
        else:
            print(api_instance.list_namespaced_pod(namespace))
    
    print("Resources defined in the YAML file have been created.")

def running_benchmark(benchmark_config):
    print("Start running benchmark.")
    benchmark_script = benchmark_config.get("test_script_path")
    benchmark_config_path = benchmark_config.get("benchmark_config_path")
    benchmark_utils.command_execute('python ' + benchmark_script + " -c " + benchmark_config_path + " -log info")
    print("Benchmark is finished.")
    
def main():
    benchmark_config = yaml_load("benchmark.yaml")
    config.load_kube_config()
    # Create an instance of the API class
    k8s_api_instance = client.CoreV1Api()
    batch_size = benchmark_config.get("batch_size")
    output_tokens = benchmark_config.get("output_tokens_to_concurrency")
    pod_num = benchmark_config.get("pod_num")
    namespace = 'default'
    for bs in batch_size:
        for pn in pod_num:
            cleanup_environment(benchmark_config, k8s_api_instance, namespace)
            deploy_llm(benchmark_config, k8s_api_instance, bs, pn, namespace)
            for ot in output_tokens:
                configure_new_testcase(benchmark_config, bs, pn, ot)
                running_benchmark(benchmark_config)

if __name__ == "__main__":
    main()