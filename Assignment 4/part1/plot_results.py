import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
import sys

def calculate_confidence_interval(data, confidence=0.90):
    """
    Calculate mean and 90% confidence interval for the given data.
    """
    n = len(data)
    mean = np.mean(data)
    std_err = stats.sem(data)  # Standard error of the mean
    
    # Calculate confidence interval
    ci = std_err * stats.t.ppf((1 + confidence) / 2, n - 1)
    
    return mean, ci

def plot_loss_experiment(csv_file):
    """
    Plot download time vs packet loss rate with 90% confidence intervals.
    """
    # Read CSV file
    df = pd.read_csv(csv_file)
    
    # Group by loss percentage and calculate statistics
    loss_rates = sorted(df['loss'].unique())
    means = []
    cis = []
    
    for loss in loss_rates:
        times = df[df['loss'] == loss]['ttc'].values
        mean, ci = calculate_confidence_interval(times)
        means.append(mean)
        cis.append(ci)
    
    # Create plot
    plt.figure(figsize=(10, 6))
    plt.errorbar(loss_rates, means, yerr=cis, marker='o', capsize=5, capthick=2,
                 linewidth=2, markersize=8, label='Mean download time')
    
    plt.xlabel('Packet Loss Rate (%)', fontsize=12)
    plt.ylabel('Download Time (seconds)', fontsize=12)
    plt.title('Download Time vs Packet Loss Rate\n(with 90% Confidence Intervals)', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=10)
    
    # Save plot
    plt.tight_layout()
    plt.savefig('loss_experiment.png', dpi=300, bbox_inches='tight')
    print(f"Plot saved as 'loss_experiment.png'")
    
    # Print statistics
    print("\n=== Loss Experiment Statistics ===")
    print(f"{'Loss Rate (%)':<15} {'Mean Time (s)':<15} {'90% CI (±)':<15} {'Min (s)':<12} {'Max (s)':<12}")
    print("-" * 75)
    for i, loss in enumerate(loss_rates):
        times = df[df['loss'] == loss]['ttc'].values
        print(f"{loss:<15} {means[i]:<15.3f} {cis[i]:<15.3f} {min(times):<12.3f} {max(times):<12.3f}")
    
    plt.show()

def plot_jitter_experiment(csv_file):
    """
    Plot download time vs delay jitter with 90% confidence intervals.
    """
    # Read CSV file
    df = pd.read_csv(csv_file)
    
    # Group by jitter and calculate statistics
    jitters = sorted(df['jitter'].unique())
    means = []
    cis = []
    
    for jitter in jitters:
        times = df[df['jitter'] == jitter]['ttc'].values
        mean, ci = calculate_confidence_interval(times)
        means.append(mean)
        cis.append(ci)
    
    # Create plot
    plt.figure(figsize=(10, 6))
    plt.errorbar(jitters, means, yerr=cis, marker='s', capsize=5, capthick=2,
                 linewidth=2, markersize=8, label='Mean download time', color='orange')
    
    plt.xlabel('Delay Jitter (ms)', fontsize=12)
    plt.ylabel('Download Time (seconds)', fontsize=12)
    plt.title('Download Time vs Delay Jitter\n(with 90% Confidence Intervals)', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=10)
    
    # Save plot
    plt.tight_layout()
    plt.savefig('jitter_experiment.png', dpi=300, bbox_inches='tight')
    print(f"Plot saved as 'jitter_experiment.png'")
    
    # Print statistics
    print("\n=== Jitter Experiment Statistics ===")
    print(f"{'Jitter (ms)':<15} {'Mean Time (s)':<15} {'90% CI (±)':<15} {'Min (s)':<12} {'Max (s)':<12}")
    print("-" * 75)
    for i, jitter in enumerate(jitters):
        times = df[df['jitter'] == jitter]['ttc'].values
        print(f"{jitter:<15} {means[i]:<15.3f} {cis[i]:<15.3f} {min(times):<12.3f} {max(times):<12.3f}")
    
    plt.show()

def verify_data_integrity(csv_file):
    """
    Verify that all transferred files have the same MD5 hash (no corruption).
    """
    df = pd.read_csv(csv_file)
    unique_hashes = df['md5_hash'].unique()
    
    print("\n=== Data Integrity Check ===")
    print(f"Total transfers: {len(df)}")
    print(f"Unique MD5 hashes: {len(unique_hashes)}")
    
    if len(unique_hashes) == 1:
        print("✓ All files transferred successfully with identical hash!")
        print(f"  MD5 Hash: {unique_hashes[0]}")
    else:
        print("✗ Warning: Different MD5 hashes detected!")
        for i, hash_val in enumerate(unique_hashes):
            count = len(df[df['md5_hash'] == hash_val])
            print(f"  Hash {i+1}: {hash_val} ({count} occurrences)")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 plot_results.py <loss|jitter>")
        print("\nExamples:")
        print("  python3 plot_results.py loss     # Plot loss experiment results")
        print("  python3 plot_results.py jitter   # Plot jitter experiment results")
        sys.exit(1)
    
    exp_type = sys.argv[1].lower()
    csv_file = f'reliability_{exp_type}.csv'
    
    try:
        # Verify data integrity first
        verify_data_integrity(csv_file)
        
        # Plot based on experiment type
        if exp_type == 'loss':
            plot_loss_experiment(csv_file)
        elif exp_type == 'jitter':
            plot_jitter_experiment(csv_file)
        else:
            print(f"Unknown experiment type: {exp_type}")
            print("Use 'loss' or 'jitter'")
            sys.exit(1)
    
    except FileNotFoundError:
        print(f"Error: Could not find {csv_file}")
        print("Make sure you have run the experiment first using:")
        print(f"  sudo python3 p1_exp.py {exp_type}")
        sys.exit(1)

if __name__ == "__main__":
    main()
