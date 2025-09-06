import subprocess
import json
import os
import time

def run_experiment():
    """
    Runs a single experiment for Part 3.
    - Assumes the server is already running.
    - Starts 10 clients (9 normal, 1 greedy).
    - Waits for all clients to finish.
    """
    with open('config.json', 'r') as f:
        config = json.load(f)

    num_clients = config.get('num_clients', 10)

    # Create a directory to store results
    if not os.path.exists("part3_results"):
        os.makedirs("part3_results")

    # NOTE: The server must be started manually on host h2 before running this.
    print("Assuming server is running on h2 (10.0.0.2)...")

    client_processes = []
    print(f"Starting {num_clients} clients...")
    
    # Start 9 normal clients
    for i in range(num_clients - 1):
        cmd = ["python3", "client.py", str(i)]
        proc = subprocess.Popen(cmd)
        client_processes.append(proc)
        
    # Start 1 greedy client
    greedy_client_id = num_clients - 1
    cmd = ["python3", "client.py", str(greedy_client_id), "--greedy"]
    proc = subprocess.Popen(cmd)
    client_processes.append(proc)
    
    # Wait for all client processes to complete
    for proc in client_processes:
        proc.wait()
        
    print("All clients finished.")

if __name__ == "__main__":
    run_experiment()