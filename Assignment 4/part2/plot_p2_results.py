#!/usr/bin/env python3
"""
Plotting script for Part 2 Congestion Control Experiments
Creates visualizations for:
1. Fixed Bandwidth - JFI and Link Utilization vs Bandwidth
2. Varying Loss - Link Utilization vs Loss Rate
3. Asymmetric Flows - JFI vs RTT
4. Background UDP - Bar chart of utilization and fairness
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import sys

# Set style for better-looking plots
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 11

def plot_fixed_bandwidth(csv_file):
    """
    Plot JFI and Link Utilization vs Bandwidth for Fixed Bandwidth experiment
    """
    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return
    
    print(f"Plotting Fixed Bandwidth from {csv_file}")
    df = pd.read_csv(csv_file)
    
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    
    # Group by bandwidth and compute mean
    grouped = df.groupby('bw').agg({
        'link_util': 'mean',
        'jfi': 'mean'
    }).reset_index()
    
    # Create figure with two y-axes
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    # Plot Link Utilization on left y-axis
    color1 = 'tab:blue'
    ax1.set_xlabel('Link Capacity (Mbps)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Link Utilization', color=color1, fontsize=12, fontweight='bold')
    line1 = ax1.plot(grouped['bw'], grouped['link_util'], 
                     color=color1, marker='o', linewidth=2, 
                     markersize=8, label='Link Utilization')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim([0, max(1.1, grouped['link_util'].max() * 1.1)])
    
    # Plot JFI on right y-axis
    ax2 = ax1.twinx()
    color2 = 'tab:orange'
    ax2.set_ylabel('Jain Fairness Index (JFI)', color=color2, fontsize=12, fontweight='bold')
    line2 = ax2.plot(grouped['bw'], grouped['jfi'], 
                     color=color2, marker='s', linewidth=2, 
                     markersize=8, label='JFI')
    ax2.tick_params(axis='y', labelcolor=color2)
    ax2.set_ylim([0, 1.1])
    
    # Add legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left', fontsize=11)
    
    # Title and layout
    plt.title('Fixed Bandwidth: Link Utilization and Fairness vs Bandwidth', 
              fontsize=14, fontweight='bold', pad=20)
    fig.tight_layout()
    
    # Save figure
    output_file = 'p2_fixed_bandwidth.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_file}")
    plt.close()
    
    # Print statistics
    print("\nFixed Bandwidth Statistics:")
    print(grouped.to_string(index=False))
    print(f"\nAverage Link Utilization: {grouped['link_util'].mean():.4f}")
    print(f"Average JFI: {grouped['jfi'].mean():.4f}")


def plot_varying_loss(csv_file):
    """
    Plot Link Utilization vs Loss Rate for Varying Loss experiment
    """
    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return
    
    print(f"\nPlotting Varying Loss from {csv_file}")
    df = pd.read_csv(csv_file)
    
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    
    # Group by loss rate and compute mean
    grouped = df.groupby('loss').agg({
        'link_util': 'mean',
        'jfi': 'mean'
    }).reset_index()
    
    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot Link Utilization vs Loss
    ax.plot(grouped['loss'], grouped['link_util'], 
            color='tab:blue', marker='o', linewidth=2.5, 
            markersize=10, label='Link Utilization')
    
    ax.set_xlabel('Packet Loss Rate (%)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Link Utilization', fontsize=12, fontweight='bold')
    ax.set_title('Varying Loss: Link Utilization vs Packet Loss Rate', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)
    ax.set_ylim([0, max(1.1, grouped['link_util'].max() * 1.1)])
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'p2_varying_loss.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_file}")
    plt.close()
    
    # Print statistics
    print("\nVarying Loss Statistics:")
    print(grouped.to_string(index=False))


def plot_asymmetric_flows(csv_file):
    """
    Plot JFI vs RTT for Asymmetric Flows experiment
    """
    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return
    
    print(f"\nPlotting Asymmetric Flows from {csv_file}")
    df = pd.read_csv(csv_file)
    
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    
    # Calculate effective RTT for client 2
    # RTT = 2 * (delay_c2_sw1 + bottleneck_delay + delay_sw2_s2)
    # Base RTT components: c1 has 5ms to sw1, bottleneck has 10ms, s2 has 5ms to sw2
    # So base RTT for c1 = 2*(5+10+5) = 40ms
    # RTT for c2 = 2*(delay_c2_ms + 10 + 5) = 2*(delay_c2_ms + 15)
    df['rtt_c2_ms'] = 2 * (df['delay_c2_ms'] + 15)
    
    # Group by RTT and compute mean
    grouped = df.groupby('rtt_c2_ms').agg({
        'jfi': 'mean',
        'link_util': 'mean'
    }).reset_index()
    
    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot JFI vs RTT
    ax.plot(grouped['rtt_c2_ms'], grouped['jfi'], 
            color='tab:orange', marker='s', linewidth=2.5, 
            markersize=10, label='Jain Fairness Index')
    
    ax.set_xlabel('Client 2 RTT (ms)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Jain Fairness Index (JFI)', fontsize=12, fontweight='bold')
    ax.set_title('Asymmetric Flows: Fairness vs RTT Asymmetry', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)
    ax.set_ylim([0, 1.1])
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'p2_asymmetric_flows.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_file}")
    plt.close()
    
    # Print statistics
    print("\nAsymmetric Flows Statistics:")
    print(grouped.to_string(index=False))
    print(f"\nAverage JFI: {grouped['jfi'].mean():.4f}")
    print(f"Average Link Utilization: {grouped['link_util'].mean():.4f}")


def plot_background_udp(csv_file):
    """
    Plot bar chart showing Link Utilization and Fairness for different UDP loads
    """
    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return
    
    print(f"\nPlotting Background UDP from {csv_file}")
    df = pd.read_csv(csv_file)
    
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    
    # Group by UDP off mean and compute mean metrics
    grouped = df.groupby('udp_off_mean').agg({
        'link_util': 'mean',
        'jfi': 'mean'
    }).reset_index()
    
    # Sort by UDP off mean (higher mean = lighter load)
    grouped = grouped.sort_values('udp_off_mean', ascending=False)
    
    # Create labels based on UDP load
    labels = []
    for off_mean in grouped['udp_off_mean']:
        if off_mean >= 1.5:
            labels.append(f'Light\n(OFF={off_mean}s)')
        elif off_mean >= 0.8:
            labels.append(f'Medium\n(OFF={off_mean}s)')
        else:
            labels.append(f'Heavy\n(OFF={off_mean}s)')
    
    # Create figure with two subplots side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    x_pos = np.arange(len(labels))
    bar_width = 0.6
    
    # Plot Link Utilization
    bars1 = ax1.bar(x_pos, grouped['link_util'], bar_width, 
                    color='tab:blue', alpha=0.8, edgecolor='black', linewidth=1.5)
    ax1.set_xlabel('UDP Background Traffic Load', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Link Utilization', fontsize=12, fontweight='bold')
    ax1.set_title('Link Utilization with Background UDP', fontsize=13, fontweight='bold')
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(labels)
    ax1.set_ylim([0, max(1.1, grouped['link_util'].max() * 1.15)])
    ax1.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.3f}',
                ha='center', va='bottom', fontweight='bold')
    
    # Plot JFI
    bars2 = ax2.bar(x_pos, grouped['jfi'], bar_width, 
                    color='tab:orange', alpha=0.8, edgecolor='black', linewidth=1.5)
    ax2.set_xlabel('UDP Background Traffic Load', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Jain Fairness Index (JFI)', fontsize=12, fontweight='bold')
    ax2.set_title('Fairness with Background UDP', fontsize=13, fontweight='bold')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(labels)
    ax2.set_ylim([0, 1.1])
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.3f}',
                ha='center', va='bottom', fontweight='bold')
    
    plt.suptitle('Background UDP Traffic: Impact on TCP Performance', 
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    # Save figure
    output_file = 'p2_background_udp.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_file}")
    plt.close()
    
    # Print statistics
    print("\nBackground UDP Statistics:")
    print(grouped.to_string(index=False))


def create_summary_report(csv_files):
    """
    Create a summary report of all experiments
    """
    print("\n" + "="*80)
    print("PART 2: CONGESTION CONTROL - EXPERIMENT SUMMARY")
    print("="*80)
    
    for exp_name, csv_file in csv_files.items():
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            # Strip whitespace from column names
            df.columns = df.columns.str.strip()
            
            print(f"\n{exp_name.upper().replace('_', ' ')}:")
            print(f"  Total trials: {len(df)}")
            print(f"  Average Link Utilization: {df['link_util'].mean():.4f}")
            print(f"  Average JFI: {df['jfi'].mean():.4f}")
            print(f"  Min JFI: {df['jfi'].min():.4f}, Max JFI: {df['jfi'].max():.4f}")
            
            # Check MD5 hashes for correctness
            if 'md5_hash_1' in df.columns and 'md5_hash_2' in df.columns:
                mismatches = df[(df['md5_hash_1'] != df['md5_hash_2']) | 
                               (df['md5_hash_1'].isna()) | 
                               (df['md5_hash_2'].isna())]
                if len(mismatches) > 0:
                    print(f"  WARNING: {len(mismatches)} trials with MD5 mismatches or missing data!")
                else:
                    print(f"  ✓ All transfers completed successfully (MD5 verified)")
    
    print("\n" + "="*80)


def main():
    """Main function to generate all plots"""
    
    # Define experiment CSV files
    csv_files = {
        'fixed_bandwidth': 'p2_fairness_fixed_bandwidth.csv',
        'varying_loss': 'p2_fairness_varying_loss.csv',
        'asymmetric_flows': 'p2_fairness_asymmetric_flows.csv',
        'background_udp': 'p2_fairness_background_udp.csv'
    }
    
    print("="*80)
    print("PART 2: CONGESTION CONTROL - PLOTTING RESULTS")
    print("="*80)
    
    # Check which files exist
    available_experiments = []
    for exp_name, csv_file in csv_files.items():
        if os.path.exists(csv_file):
            available_experiments.append(exp_name)
            print(f"✓ Found: {csv_file}")
        else:
            print(f"✗ Not found: {csv_file} (skipping)")
    
    if not available_experiments:
        print("\nNo CSV files found! Run experiments first using p2_exp.py")
        return
    
    print(f"\nGenerating plots for {len(available_experiments)} experiment(s)...\n")
    
    # Generate plots for each available experiment
    if 'fixed_bandwidth' in available_experiments:
        plot_fixed_bandwidth(csv_files['fixed_bandwidth'])
    
    if 'varying_loss' in available_experiments:
        plot_varying_loss(csv_files['varying_loss'])
    
    if 'asymmetric_flows' in available_experiments:
        plot_asymmetric_flows(csv_files['asymmetric_flows'])
    
    if 'background_udp' in available_experiments:
        plot_background_udp(csv_files['background_udp'])
    
    # Create summary report
    create_summary_report(csv_files)
    
    print(f"\nPlotting complete! Generated {len(available_experiments)} plot(s).")
    print("\nGenerated files:")
    for exp_name in available_experiments:
        png_file = f"p2_{exp_name}.png"
        if os.path.exists(png_file):
            print(f"  - {png_file}")


if __name__ == '__main__':
    main()
