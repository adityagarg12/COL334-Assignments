#!/usr/bin/env python3

import json
import os
import time
import glob
import numpy as np
import subprocess
# import matplotlib.pyplot as plt
import csv

class Runner:
    def __init__(self, config_file='config.json'):
        with open(config_file, 'r') as f:
            self.config = json.load(f)

        self.server_ip = self.config['server_ip']
        self.port = self.config['port']
        self.num_clients = self.config['num_clients']
        self.c = self.config['c']  # Batch size for greedy client
        self.p = self.config['p']  # Offset (always 0)
        self.k = self.config['k']  # Words per request (always 5)

        print(f"Config: {self.num_clients} clients, c={self.c}, p={self.p}, k={self.k}")

    def cleanup_logs(self):
        """Clean old log files"""
        os.makedirs("logs", exist_ok=True)
        logs = glob.glob("logs/*.log")
        for log in logs:
            os.remove(log)
        print("Cleaned old logs")

    def parse_logs(self):
        """
        Parse log files and return completion times
        Return: {'rogue': [times], 'normal': [times]}
        """
        results = {'rogue': [], 'normal': []}

        # Look for log files
        log_files = glob.glob("logs/client_*_time.log")

        for log_file in log_files:
            try:
                with open(log_file, 'r') as f:
                    completion_time = float(f.read().strip())

                # Determine if this is rogue or normal client based on filename
                filename = os.path.basename(log_file)
                if 'rogue' in filename:
                    results['rogue'].append(completion_time)
                else:
                    results['normal'].append(completion_time)

            except Exception as e:
                print(f"Error parsing {log_file}: {e}")

        print(f"Parsed logs: {len(results['rogue'])} rogue, {len(results['normal'])} normal")
        return results

    def calculate_jfi(self, completion_times):
        """
        Calculate Jain's Fairness Index for completion times
        JFI runs under the "more is better" policy, so we use throughput (1/time)
        Formula: JFI = (sum of utilities)^2 / (n * sum of utilities^2)
        """
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
        """Run single experiment with given c value using Mininet"""
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

            # Start server (using our server.py)
            print("Starting server...")
            
            server_proc = server.popen("python3 server.py > logs/server.log 2>&1", shell=True)
            time.sleep(3)  # Give server time to start

            # Start clients
            print("Starting clients...")

            # Client 1 is rogue (batch size c)
            rogue_proc = clients[0].popen(f"python3 client.py --batch-size {c_value} --client-id rogue")

            # Clients 2-N are normal (batch size 1)
            normal_procs = []
            for i in range(1, self.num_clients):
                proc = clients[i].popen(f"python3 client.py --batch-size 1 --client-id normal_{i+1}")
                normal_procs.append(proc)

            # Wait for all clients
            print("Waiting for clients to complete...")
            rogue_proc.wait()
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
        """Run experiments with c from 1 to 10 (as specified in assignment)"""
        c_values = list(range(1, 11))  # c from 1 to 10 as per assignment
        all_results = {}
        jfi_values = []

        print("Running experiments with varying c values (1 to 10)...")

        for c in c_values:
            print(f"\n{'='*60}")
            print(f"Testing c = {c}")
            print(f"{'='*60}")

            results = self.run_experiment(c)
            all_results[c] = results

            # Combine all completion times for JFI calculation
            all_times = results['rogue'] + results['normal']
            jfi = self.calculate_jfi(all_times)
            jfi_values.append(jfi)

            print(f"Results for c={c}:")
            print(f"  Rogue completion times: {results['rogue']}")
            print(f"  Normal completion times: {results['normal']}")
            print(f"  JFI: {jfi:.4f}")

        # Save results to CSV
        self.save_results_to_csv(c_values, jfi_values, all_results)

        # Plot results
        # self.plot_jfi_vs_c(c_values, jfi_values)

        return c_values, jfi_values, all_results

    def save_results_to_csv(self, c_values, jfi_values, all_results):
        """Save results to CSV file"""
        with open('part3_results.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['c_value', 'jfi', 'rogue_times', 'normal_times', 'avg_rogue_time', 'avg_normal_time'])

            for i, c in enumerate(c_values):
                rogue_times = all_results[c]['rogue']
                normal_times = all_results[c]['normal']
                avg_rogue = np.mean(rogue_times) if rogue_times else 0
                avg_normal = np.mean(normal_times) if normal_times else 0

                writer.writerow([
                    c, 
                    jfi_values[i], 
                    '|'.join(map(str, rogue_times)),
                    '|'.join(map(str, normal_times)),
                    avg_rogue,
                    avg_normal
                ])

        print("Results saved to part3_results.csv")

    # def plot_jfi_vs_c(self, c_values, jfi_values):
    #     """Plot JFI values vs c values"""
    #     plt.figure(figsize=(12, 8))

    #     # Main plot
    #     plt.plot(c_values, jfi_values, 'bo-', linewidth=3, markersize=10, label='JFI')

    #     # Add annotations for key points
    #     for i, (c, jfi) in enumerate(zip(c_values, jfi_values)):
    #         plt.annotate(f'{jfi:.3f}', (c, jfi), textcoords="offset points", 
    #                    xytext=(0,15), ha='center', fontsize=10, fontweight='bold')

    #     # Formatting
    #     plt.xlabel('c (Number of back-to-back requests by greedy client)', fontsize=14, fontweight='bold')
    #     plt.ylabel('Jain\'s Fairness Index (JFI)', fontsize=14, fontweight='bold')
    #     plt.title('Part 3: Fairness vs Greedy Client Behavior\n(FCFS Scheduling)', fontsize=16, fontweight='bold', pad=20)
    #     plt.grid(True, alpha=0.3, linestyle='--')
    #     plt.ylim(0, 1.1)
    #     plt.xlim(0.5, 10.5)
    #     plt.xticks(c_values)

    #     # Add horizontal line at JFI=1.0 (perfect fairness)
    #     plt.axhline(y=1.0, color='r', linestyle='--', alpha=0.7, label='Perfect Fairness (JFI=1.0)')

    #     # Add text box with explanation
    #     textstr = f'Higher JFI = More Fair\nJFI Range: {min(jfi_values):.3f} - {max(jfi_values):.3f}'
    #     props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    #     plt.text(0.02, 0.98, textstr, transform=plt.gca().transAxes, fontsize=11,
    #             verticalalignment='top', bbox=props)

    #     plt.legend(fontsize=12)
    #     plt.tight_layout()
    #     plt.savefig('p3_plot.png', dpi=300, bbox_inches='tight')
    #     plt.show()
    #     print("Plot saved as p3_plot.png")

def main():
    runner = Runner()

    # Run experiments with varying c values
    c_values, jfi_values, all_results = runner.run_varying_c()

    # Print comprehensive summary
    print(f"\n{'='*80}")
    print("PART 3 EXPERIMENT SUMMARY - FCFS SCHEDULING")
    print(f"{'='*80}")
    print("c\tJFI\tΔ JFI\tTrend\t\tInterpretation")
    print("-" * 75)

    for i, (c, jfi) in enumerate(zip(c_values, jfi_values)):
        if i == 0:
            trend = "baseline"
            delta = "N/A"
            interpretation = "Normal behavior"
        else:
            prev_jfi = jfi_values[i-1]
            delta = jfi - prev_jfi
            if delta > 0.01:
                trend = "↑ improving"
                interpretation = "Unexpected improvement"
            elif delta < -0.01:
                trend = "↓ degrading"
                interpretation = "Fairness deteriorating"
            else:
                trend = "→ stable"
                interpretation = "Minimal change"

        delta_str = f"{delta:+.3f}" if isinstance(delta, float) else delta
        print(f"{c}\t{jfi:.4f}\t{delta_str}\t{trend:<12}\t{interpretation}")

    # Analysis
    fairness_change = jfi_values[-1] - jfi_values[0]
    print(f"\nOVERALL ANALYSIS:")
    print(f"- Initial JFI (c=1): {jfi_values[0]:.4f}")
    print(f"- Final JFI (c=10): {jfi_values[-1]:.4f}")
    print(f"- Total change: {fairness_change:+.4f}")

    if fairness_change < -0.1:
        conclusion = "SIGNIFICANT fairness degradation with greedy behavior"
    elif fairness_change < -0.05:
        conclusion = "MODERATE fairness degradation with greedy behavior"
    elif fairness_change > 0.05:
        conclusion = "UNEXPECTED fairness improvement (possible measurement error)"
    else:
        conclusion = "MINIMAL impact of greedy behavior on fairness"

    print(f"- Conclusion: {conclusion}")

    print(f"\nThis demonstrates that FCFS scheduling {'allows' if fairness_change < -0.05 else 'does not allow'} greedy clients")
    print("to significantly monopolize server resources, highlighting the need for fairer scheduling policies.")

if __name__ == '__main__':
    main()
