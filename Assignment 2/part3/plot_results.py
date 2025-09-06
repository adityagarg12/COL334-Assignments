import subprocess
import json
import os
import numpy as np
import matplotlib.pyplot as plt

def jains_fairness_index(x):
    """Calculate Jain's Fairness Index for a list of values."""
    if not x:
        return 0
    x = np.array(x)
    if np.sum(x) == 0:
        return 1.0 # Perfect fairness if all values are 0
    return (np.sum(x) ** 2) / (len(x) * np.sum(x ** 2))

def main():
    """
    Run experiments for c=1 to 10, calculate JFI, and plot the results.
    """
    c_values = range(1, 11)
    jfi_scores = []
    num_clients = 10 # As specified in the assignment

    for c in c_values:
        print(f"\n----- Running experiment for c = {c} -----")

        # Update c in config.json
        with open('config.json', 'r+') as f:
            config = json.load(f)
            config['c'] = c
            f.seek(0)
            json.dump(config, f, indent=2)
            f.truncate()
        
        # Run the experiment using runner.py
        subprocess.run(["python3", "runner.py"], check=True)

        # Collect completion times
        completion_times = []
        results_dir = "part3_results"
        for i in range(num_clients):
            try:
                with open(os.path.join(results_dir, f"client_{i}_time.txt"), 'r') as f:
                    completion_times.append(float(f.read().strip()))
            except FileNotFoundError:
                print(f"Warning: Result file for client {i} not found for c={c}.")
                completion_times.append(0) # Assume 0 if not found

        # Calculate JFI for this value of c
        jfi = jains_fairness_index(completion_times)
        jfi_scores.append(jfi)
        print(f"Jain's Fairness Index for c = {c}: {jfi:.4f}")

    # Plotting the results
    plt.figure(figsize=(10, 6))
    plt.plot(c_values, jfi_scores, marker='o', linestyle='-')
    plt.title("Fairness of FCFS Server with a Greedy Client")
    plt.xlabel("Number of Back-to-Back Requests by Greedy Client (c)")
    plt.ylabel("Jain's Fairness Index (JFI)")
    plt.grid(True)
    plt.xticks(c_values)
    plt.ylim(0, 1.1)
    
    # Save the plot
    plot_filename = "p3_plot.png"
    plt.savefig(plot_filename)
    print(f"\nPlot saved as {plot_filename}")
    plt.show()


if __name__ == "__main__":
    main()