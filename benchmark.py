import os
import benchmark_utils
from kubernetes import client, config, watch
import time
        
def cleanup_environment(benchmark_config, api_instance, namespace, llm_engine):
    deploy_yaml = benchmark_config.get("inference_deploy_yaml_path")
    benchmark_utils.command_execute('kubectl delete -f ' + deploy_yaml)
    if llm_engine == "torchserve":
        kill_pod_binary = benchmark_config.get("kill_pod_binary_path")
        benchmark_utils.command_execute('bash ' + kill_pod_binary)

    # List all pods in the specified namespace
    api_response = api_instance.list_namespaced_pod(namespace)
    while api_response.items:
        time.sleep(3)
        api_response = api_instance.list_namespaced_pod(namespace)
    print("Resources defined in the YAML file have been deleted.")
    
def configure_new_testcase(benchmark_config, batch_size, pod_num, output_token, input_token, llm_engine):
    print("Start configure_new_testcase.")
    # Change the benchmark config
    benchmark_config_path = benchmark_config.get("benchmark_config_path")
    # Load the YAML file
    duration_time = benchmark_config.get("duration")
    concurrency = batch_size * pod_num
    output_name = benchmark_config.get("output").get("name")
    output_format = benchmark_config.get("output").get("format")
    output_file_name = output_name + "-input_tokens" + str(input_token) + "-output_tokens" + str(output_token) + "-batch" + str(batch_size) + "-pod" + str(pod_num) + "." + output_format
    output_dir = benchmark_config.get("output").get("dir")
    benchmark_config_data = benchmark_utils.yaml_load(benchmark_config_path)
    benchmark_config_data['output']['file'] = output_file_name
    benchmark_config_data['output']['dir'] = output_dir
    benchmark_config_data['load_options']['concurrency'] = concurrency
    benchmark_config_data['load_options']['duration'] = duration_time
    benchmark_config_data['dataset']['max_output_tokens'] = output_token if output_token != -1 else 128
    benchmark_config_data['dataset']['min_output_tokens'] = output_token if output_token != -1 else 128
    benchmark_config_data['dataset']['max_input_tokens'] = input_token if output_token != -1 else 128
    benchmark_config_data['dataset']['min_input_tokens'] = input_token if output_token != -1 else 128

    benchmark_config_data['plugin_options']['constant_output_tokens'] = output_token
    benchmark_config_data['plugin_options']['model_name'] = benchmark_config.get("model_name")
    benchmark_config_data['plugin_options']['model_path'] = benchmark_config.get("model_path")
    if llm_engine == "torchserve":
        benchmark_config_data['plugin'] = "torch_serve_plugin"
    else:
        benchmark_config_data['plugin'] = "openai_plugin"
        benchmark_config_data['dataset']['enable_constant'] = benchmark_config.get("enable_constant")
    benchmark_utils.yaml_dump(benchmark_config_data, benchmark_config_path)
    print("Finish configure_new_testcase.")

def deploy_llm(benchmark_config, api_instance, batch_size, pod_num, namespace, llm_engine):
    print("Start deploy_llm.")
    # Change the pod number in the deploy yaml file
    deploy_yaml = benchmark_config.get("inference_deploy_yaml_path")
    deploy_data = benchmark_utils.yaml_load(deploy_yaml)
    deploy_data['spec']['predictor']['minReplicas'] = pod_num
    deploy_data['spec']['predictor']['maxReplicas'] = pod_num
    benchmark_utils.yaml_dump(deploy_data, deploy_yaml)
    
    # Change the batch size in the llm config for torchserve
    if llm_engine == "torchserve":
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
    time.sleep(60)
    print("Resources defined in the YAML file have been created.")

def running_benchmark(benchmark_config):
    print("Start running benchmark.")
    benchmark_script = benchmark_config.get("test_script_path")
    benchmark_config_path = benchmark_config.get("benchmark_config_path")
    benchmark_utils.command_execute('python ' + benchmark_script + " -c " + benchmark_config_path + " -log info")
    print("Benchmark is finished.")
    
def main():
    benchmark_config = benchmark_utils.yaml_load("benchmark.yaml")
    config.load_kube_config()
    # Create an instance of the API class
    k8s_api_instance = client.CoreV1Api()
    
    llm_engine = benchmark_config.get("llm_engine")
    namespace = 'default'
    batch_size = benchmark_config.get("batch_size")
    output_tokens = benchmark_config.get("output_tokens")
    input_tokens = benchmark_config.get("input_tokens")
    pod_num = benchmark_config.get("pod_num") 
    for bs in batch_size:
        for pn in pod_num:
            cleanup_environment(benchmark_config, k8s_api_instance, namespace, llm_engine)
            deploy_llm(benchmark_config, k8s_api_instance, bs, pn, namespace, llm_engine)
            for ot in output_tokens:
                for it in input_tokens:
                    configure_new_testcase(benchmark_config, bs, pn, ot, it, llm_engine)
                    running_benchmark(benchmark_config)

    output_dir =  benchmark_config.get("output").get("dir")
    csv_file_name = benchmark_config.get("output").get("csv")
    benchmark_utils.generate_csv(output_dir, csv_file_name)
    benchmark_utils.generate_graphs(output_dir + csv_file_name)

if __name__ == "__main__":
    main()