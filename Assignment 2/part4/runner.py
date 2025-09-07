import json
import os
import time
import glob
import numpy as np
import subprocess
import csv

class Runner:
    def __init__(self, config_file='config.json'):
        with open(config_file, 'r') as f:
            self.config = json.load(f)

        self.server_ip = self.config['server_ip']
        self.port = self.config.get('port', 5000)
        self.num_clients = self.config['num_clients']
        self.k = self.config['k']

        print(f"Config: {self.num_clients} clients, k={self.k}")

    def cleanup_logs(self):
        os.makedirs("logs", exist_ok=True)
        for log in glob.glob("logs/*.log"):
            os.remove(log)
        print("Cleaned old logs")

    def parse_logs(self):
        results = {'rogue': [], 'normal': []}
        for log_file in glob.glob("logs/client_*_time.log"):
            try:
                with open(log_file, 'r') as f:
                    completion_time = float(f.read().strip())
                if 'rogue' in os.path.basename(log_file):
                    results['rogue'].append(completion_time)
                else:
                    results['normal'].append(completion_time)
            except Exception as e:
                print(f"Error parsing {log_file}: {e}")
        print(f"Parsed logs: {len(results['rogue'])} rogue, {len(results['normal'])} normal")
        return results

    def calculate_jfi(self, completion_times):
        if not completion_times:
            return 0.0
        n = len(completion_times)
        throughputs = [1 / (t + 1e-9) for t in completion_times]
        sum_throughputs = sum(throughputs)
        sum_squares = sum(t**2 for t in throughputs)
        if sum_squares == 0:
            return 1.0
        return (sum_throughputs**2) / (n * sum_squares)

    def run_experiment(self, c_value):
        print(f"Running experiment with c={c_value}")
        self.cleanup_logs()
        
        from topology import create_network
        net = create_network(num_clients=self.num_clients)
        
        try:
            server = net.get('server')
            clients = [net.get(f'client{i+1}') for i in range(self.num_clients)]

            print("Starting server...")
            server_proc = server.popen("python3 server.py", stdout=open("logs/server.log", "w"), stderr=subprocess.STDOUT, shell=True)
            time.sleep(3)

            print("Starting clients...")
            rogue_proc = clients[0].popen(f"python3 client.py --batch-size {c_value} --client-id rogue")
            normal_procs = [clients[i].popen(f"python3 client.py --batch-size 1 --client-id normal_{i+1}") for i in range(1, self.num_clients)]

            print("Waiting for clients to complete...")
            rogue_proc.wait()
            for proc in normal_procs:
                proc.wait()
            print("All clients completed")

            server_proc.terminate()
            server_proc.wait()
            
            time.sleep(1)
            return self.parse_logs()
        finally:
            net.stop()

    def run_varying_c(self):
        c_values = list(range(1, 11))
        all_results = {}
        jfi_values = []

        for c in c_values:
            print(f"\n{'='*60}\nTesting c = {c}\n{'='*60}")
            results = self.run_experiment(c)
            all_results[c] = results
            all_times = results['rogue'] + results['normal']
            jfi = self.calculate_jfi(all_times)
            jfi_values.append(jfi)
            print(f"Results for c={c}: JFI = {jfi:.4f}")

        self.save_results_to_csv(c_values, jfi_values)

    def save_results_to_csv(self, c_values, jfi_values):
        with open('part4_results.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['c_value', 'jfi'])
            for c, jfi in zip(c_values, jfi_values):
                writer.writerow([c, jfi])
        print("Results saved to part4_results.csv")

if __name__ == '__main__':
    runner = Runner()
    runner.run_varying_c()
