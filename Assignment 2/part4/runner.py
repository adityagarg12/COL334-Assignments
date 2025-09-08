#!/usr/bin/env python3

# import json
import os
import time
import glob
import numpy as np
import subprocess

import csv

class Runner:
    def __init__(self, config_file='config.json'):
       
        self.config = {}
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//") or line.startswith("#"):
                    continue
                if '"server_ip"' in line:
                    colon = line.find(":")
                    quote1 = line.find('"', colon)
                    quote2 = line.find('"', quote1 + 1)
                    self.config['server_ip'] = line[quote1 + 1:quote2]
                elif '"port"' in line or '"server_port"' in line:
                    colon = line.find(":")
                    num = ''.join(c for c in line[colon+1:] if c.isdigit())
                    self.config['port'] = int(num)
                elif '"num_clients"' in line:
                    colon = line.find(":")
                    num = ''.join(c for c in line[colon+1:] if c.isdigit())
                    self.config['num_clients'] = int(num)
                elif '"c"' in line:
                    colon = line.find(":")
                    num = ''.join(c for c in line[colon+1:] if c.isdigit())
                    self.config['c'] = int(num)
                elif '"p"' in line:
                    colon = line.find(":")
                    num = ''.join(c for c in line[colon+1:] if c.isdigit())
                    self.config['p'] = int(num)
                elif '"k"' in line:
                    colon = line.find(":")
                    num = ''.join(c for c in line[colon+1:] if c.isdigit())
                    self.config['k'] = int(num)
                elif '"filename"' in line:
                    colon = line.find(":")
                    quote1 = line.find('"', colon)
                    quote2 = line.find('"', quote1 + 1)
                    self.config['filename'] = line[quote1 + 1:quote2]

        self.server_ip = self.config['server_ip']
        self.port = self.config['port']
        self.num_clients = self.config['num_clients']
        self.c = self.config['c']
        self.p = self.config['p']
        self.k = self.config['k']
        self.filename = self.config['filename']

    def cleanup_logs(self):
       
        os.makedirs("logs", exist_ok=True)
        logs = glob.glob("logs/*.log")
        for log in logs:
            os.remove(log)
        

    def parse_logs(self):
        
        results = {'greedy': [], 'normal': []}

        log_files = glob.glob("logs/client_*_time.log")

        for log_file in log_files:
            try:
                with open(log_file, 'r') as f:
                    completion_time = float(f.read().strip())

                filename = os.path.basename(log_file)
                if 'greedy' in filename:
                    results['greedy'].append(completion_time)
                else:
                    results['normal'].append(completion_time)

            except Exception as e:
                print(f"Error parsing {log_file}: {e}")

        print(f"Parsed logs: {len(results['greedy'])} greedy, {len(results['normal'])} normal")
        return results

    def calculate_jfi(self, completion_times):

        if not completion_times or len(completion_times) == 0:
            return 0

        n = len(completion_times)

        throughputs = [1/(t + 1e-6) for t in completion_times]

        sum_throughputs = sum(throughputs)
        sum_squares = sum(t*t for t in throughputs)

        if sum_squares == 0:
            return 0

        jfi = (sum_throughputs ** 2) / (n * sum_squares)
        return jfi

    def run_experiment(self, c_value):
       
        print(f"Running experiment with c={c_value}")

        self.cleanup_logs()

        from topology import create_network
        net = create_network(num_clients=self.num_clients)

        try:

            server = net.get('server')
            clients = [net.get(f'client{i+1}') for i in range(self.num_clients)]  
                    
            server_proc = server.popen("python3 server.py > logs/server.log 2>&1", shell=True)
            time.sleep(3)        

            greedy_proc = clients[0].popen(f"python3 client.py --batch-size {c_value} --client-id greedy")

            normal_procs = []
            for i in range(1, self.num_clients):
                proc = clients[i].popen(f"python3 client.py --batch-size 1 --client-id normal_{i+1}")
                normal_procs.append(proc)

            print("Waiting for clients to complete...")
            greedy_proc.wait()
            for proc in normal_procs:
                proc.wait()

            print("All clients completed")

            server_proc.terminate()
            server_proc.wait()
            time.sleep(2)

    
            time.sleep(1)  
            results = self.parse_logs()
            return results

        finally:
            net.stop()

    def run_for_config_c(self):
        c_value = self.c
        results = self.run_experiment(c_value)
        all_results = {c_value: results}
        all_times = results['greedy'] + results['normal']
        jfi = self.calculate_jfi(all_times)
        jfi_values = [jfi]
        c_values = [c_value]
        self.save_results_to_csv(c_values, jfi_values, all_results)
        return c_values, jfi_values, all_results

    def save_results_to_csv(self, c_values, jfi_values, all_results):
       
        with open('part4_results.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['c_value', 'jfi', 'greedy_times', 'normal_times', 'avg_greedy_time', 'avg_normal_time'])

            for i, c in enumerate(c_values):
                greedy_times = all_results[c]['greedy']
                normal_times = all_results[c]['normal']
                avg_greedy = np.mean(greedy_times) if greedy_times else 0
                avg_normal = np.mean(normal_times) if normal_times else 0

                writer.writerow([
                    c, 
                    jfi_values[i], 
                    '|'.join(map(str, greedy_times)),
                    '|'.join(map(str, normal_times)),
                    avg_greedy,
                    avg_normal
                ])

        print("Results saved to part4_results.csv")

   

def main():
    runner = Runner()

    # Run experiments with varying c values
    c_values, jfi_values, all_results = runner.run_for_config_c()

  
   

   

if __name__ == '__main__':
    main()
