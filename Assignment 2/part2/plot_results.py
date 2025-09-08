import matplotlib.pyplot as plt
import csv
import os

OUTPUT_DIR = "output"
input_file = os.path.join(OUTPUT_DIR, "results.csv")
output_plot = os.path.join(OUTPUT_DIR, "p2_plot.png")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# If old plot exists (possibly root-owned), remove it
if os.path.exists(output_plot):
    try:
        os.remove(output_plot)
        print(f"Removed old plot: {output_plot}")
    except PermissionError:
        print(f"Permission error removing old plot. Try: sudo rm {output_plot}")
        exit(1)

clients = []
avg_times = []
ci95 = []

with open(input_file) as f:
    reader = csv.DictReader(f)
    for row in reader:
        clients.append(int(row["clients"]))
        avg_times.append(float(row["avg_time"]))
        ci95.append(float(row["ci95"]))

plt.errorbar(clients, avg_times, yerr=ci95, fmt='-o', capsize=5, label="Completion Time")
plt.xlabel("Number of Clients")
plt.ylabel("Average Completion Time (s)")
plt.title("Part 2: Avg Completion Time per Client vs Num Clients")
plt.legend()
plt.grid(True)
plt.savefig(output_plot)
plt.show()

print(f"\nPlot saved as {output_plot}")
