import time
import statistics
import os
from topology import create_network
from mininet.log import setLogLevel

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_experiment(num_clients, repetitions):
    completion_times = []

    for _ in range(repetitions):
        net = create_network(num_clients=num_clients)
        
        server = net.get('server')
        clients = [net.get(f'client{i+1}') for i in range(num_clients)]

        server.cmd('python3 server.py &')
        time.sleep(1)

        start_time = time.time()

        client_processes = []
        for client in clients:
            proc = client.popen('python3 client.py')
            client_processes.append(proc)
        
        for proc in client_processes:
            proc.wait()

        end_time = time.time()
        duration = end_time - start_time
        completion_times.append(duration)
        
        server.cmd('kill %python3')
        net.stop()

    avg = statistics.mean(completion_times)
    ci95 = 1.96 * (statistics.pstdev(completion_times) / (len(completion_times) ** 0.5))
    return avg, ci95

if __name__ == "__main__":
    setLogLevel('info')

    max_clients = 32
    repetitions = 5
    results = []

    for n in range(1, max_clients + 1, 4):
        avg, ci95 = run_experiment(n, repetitions)
        results.append((n, avg, ci95))

    output_file = os.path.join(OUTPUT_DIR, "results.csv")
    with open(output_file, "w") as f:
        f.write("clients,avg_time,ci95\n")
        for n, avg, ci95 in results:
            f.write(f"{n},{avg},{ci95}\n")

