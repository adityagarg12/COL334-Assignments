import matplotlib.pyplot as plt
import pandas as pd
import sys
import os

# Default CSV and output plot file names
default_csv = 'part3_results.csv'
default_plot = 'output/p3_plot.png'

def plot_results(csv_file=default_csv, plot_file=default_plot):
    if not os.path.exists(csv_file):
        print(f"CSV file not found: {csv_file}")
        return
    df = pd.read_csv(csv_file)
    if df.empty:
        print("CSV file is empty.")
        return
    # Expecting columns: 'c' and 'JFI' (or similar)
    # Try to find appropriate columns
    c_col = None
    jfi_col = None
    for col in df.columns:
        if col.lower() == 'c_value':
            c_col = col
        if 'jfi' in col.lower() or 'fairness' in col.lower():
            jfi_col = col
    if c_col is None or jfi_col is None:
        print("CSV must contain columns for 'c' and 'JFI'.")
        print(f"Found columns: {list(df.columns)}")
        return
    plt.figure(figsize=(8, 5))
    plt.plot(df[c_col], df[jfi_col], marker='o', linestyle='-')
    plt.xlabel('Number of Back-to-Back Requests by Greedy Client (c)')
    plt.ylabel("Jain's Fairness Index (JFI)")
    plt.title("JFI vs c")
    plt.grid(True)
    plt.xticks(df[c_col])
    plt.ylim(0, 1.1)
    plt.tight_layout()
    # Save plot as 'plot_part3.png' regardless of plot_file argument
    output_plot = 'plot_part3.png'
    plt.savefig(output_plot)
    print(f"Plot saved to {output_plot}")


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else default_csv
    # Ignore plot_file argument, always save as 'plot_part3.png'
    plot_results(csv_file, 'plot_part3.png')