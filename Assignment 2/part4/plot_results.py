import matplotlib.pyplot as plt
import csv
import os

def plot_part4_results(csv_file='part4_results.csv', plot_file='p4_plot.png'):
    if not os.path.exists(csv_file):
        print(f"Error: Results file not found: '{csv_file}'. Please run the experiment first.")
        return

    c_values = []
    jfi_values = []

    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                c_values.append(int(row['c_value']))
                jfi_values.append(float(row['jfi']))
    except (IOError, ValueError, KeyError) as e:
        print(f"Error reading or parsing CSV file: {e}")
        return

    plt.figure(figsize=(10, 6))
    plt.plot(c_values, jfi_values, marker='o', linestyle='-', color='g', label='Round-Robin')
    
    plt.xlabel('Greedy Client Back-to-Back Requests (c)')
    plt.ylabel("Jain's Fairness Index (JFI)")
    plt.title("Fairness Analysis: Round-Robin Scheduling vs. Greedy Client")
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    
    plt.xticks(c_values)
    plt.ylim(0, 1.1)
    
    # Add a line for perfect fairness for context
    plt.axhline(y=1.0, color='r', linestyle=':', linewidth=1.5, label='Perfect Fairness')
    
    plt.legend()
    plt.tight_layout()

    plt.savefig(plot_file)
    print(f"Plot saved successfully to {plot_file}")

if __name__ == "__main__":
    plot_part4_results()
