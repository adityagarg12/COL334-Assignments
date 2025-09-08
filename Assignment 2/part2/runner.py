import subprocess
import time
import statistics
import json
import os

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_experiment(num_clients, repetitions):
    completion_times = []

    for rep in range(repetitions):
        clients = []
        start_time = time.time()

        for _ in range(num_clients):
            p = subprocess.Popen(
                ["python3", "client.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            clients.append(p)

        for p in clients:
            p.wait()

        end_time = time.time()
        duration = end_time - start_time
        completion_times.append(duration)

    avg = statistics.mean(completion_times)
    ci95 = 1.96 * (statistics.pstdev(completion_times) / (len(completion_times) ** 0.5))
    return avg, ci95

if __name__ == "__main__":
    with open("config.json") as f:
        cfg = json.load(f)

    repetitions = 5
    results = []

    for n in range(1, cfg["num_clients"] + 1,4): 
        avg, ci95 = run_experiment(n, repetitions)
        results.append((n, avg, ci95))

    output_file = os.path.join(OUTPUT_DIR, "results.csv")
    with open(output_file, "w") as f:
        f.write("clients,avg_time,ci95\n")
        for n, avg, ci95 in results:
            f.write(f"{n},{avg},{ci95}\n")

