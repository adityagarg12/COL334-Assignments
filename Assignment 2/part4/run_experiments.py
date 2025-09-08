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
        self.num_clients = 10
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

        # Look for log files
        log_files = glob.glob("logs/client_*_time.log")

        for log_file in log_files:
            try:
                with open(log_file, 'r') as f:
                    completion_time = float(f.read().strip())

                # Determine if this is rogue or normal client based on filename
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

        # Convert completion times to throughput (inverse)
        # Add small epsilon to avoid division by zero
        throughputs = [1/(t + 1e-6) for t in completion_times]

        sum_throughputs = sum(throughputs)
        sum_squares = sum(t*t for t in throughputs)

        if sum_squares == 0:
            return 0

        jfi = (sum_throughputs ** 2) / (n * sum_squares)
        return jfi

    def run_experiment(self, c_value):
       
        print(f"Running experiment with c={c_value}")

        # Clean logs
        self.cleanup_logs()

        # Create network using provided topology
        from topology import create_network
        net = create_network(num_clients=self.num_clients)

        try:
            # Get hosts
            server = net.get('server')
            clients = [net.get(f'client{i+1}') for i in range(self.num_clients)]

        
           
            
            server_proc = server.popen("python3 server.py > logs/server.log 2>&1", shell=True)
            time.sleep(3)  # Give server time to start

           

            # Client 1 is greedy (batch size c)
            greedy_proc = clients[0].popen(f"python3 client.py --batch-size {c_value} --client-id greedy")

            # Clients 2-N are normal (batch size 1)
            normal_procs = []
            for i in range(1, self.num_clients):
                proc = clients[i].popen(f"python3 client.py --batch-size 1 --client-id normal_{i+1}")
                normal_procs.append(proc)

            # Wait for all clients
            print("Waiting for clients to complete...")
            greedy_proc.wait()
            for proc in normal_procs:
                proc.wait()

            print("All clients completed")

            # Stop server
            server_proc.terminate()
            server_proc.wait()
            time.sleep(2)

            # Parse results
            time.sleep(1)  # Give time for log files to be written
            results = self.parse_logs()
            return results

        finally:
            net.stop()

    def run_varying_c(self):
      
        c_values = list(range(1, 11))  # c from 1 to 10 as per assignment
        all_results = {}
        jfi_values = []

        

        for c in c_values:
           

            results = self.run_experiment(c)
            all_results[c] = results

          
            all_times = results['greedy'] + results['normal']
            jfi = self.calculate_jfi(all_times)
            jfi_values.append(jfi)

           

        # Save results to CSV
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
    c_values, jfi_values, all_results = runner.run_varying_c()

  
   

   

if __name__ == '__main__':
    main()
