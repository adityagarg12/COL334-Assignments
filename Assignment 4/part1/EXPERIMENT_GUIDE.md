# Assignment 4 Part 1 - Reliability Analysis Guide

## Overview
This guide explains how to analyze your reliable UDP file transfer protocol using Mininet experiments.

## Files Description

1. **p1_server.py** - UDP server with sliding window and SACK support
2. **p1_client.py** - UDP client that receives files reliably
3. **p1_exp.py** - Mininet experiment runner for testing with packet loss and jitter
4. **plot_results.py** - Script to plot results with 90% confidence intervals
5. **data.txt** - 6.2 MB file to transfer during experiments

## Prerequisites

### Install Required Packages
```bash
# Install Python packages
pip3 install pandas matplotlib scipy numpy

# Ensure Mininet is installed
sudo apt-get install mininet

# Install Ryu controller (if not already installed)
pip3 install ryu
```

## Running the Experiments

### Step 1: Start the Ryu Controller

Open a **new terminal** and run:
```bash
ryu-manager ryu.app.simple_switch_13
```

Keep this terminal running throughout all experiments.

### Step 2: Run Loss Experiment

In another terminal, navigate to the part1 directory and run:
```bash
cd "/home/aditya12/COL334-Assignments/Assignment 4/part1"
sudo python3 p1_exp.py loss
```

This will:
- Test packet loss rates: 1%, 2%, 3%, 4%, 5%
- Keep delay fixed at 20ms
- Run 5 iterations for each loss rate
- Save results to `reliability_loss.csv`

**Expected duration:** ~5-10 minutes

### Step 3: Run Jitter Experiment

```bash
sudo python3 p1_exp.py jitter
```

This will:
- Test delay jitter: 20ms, 40ms, 60ms, 80ms, 100ms
- Keep packet loss fixed at 1%
- Keep base delay at 20ms
- Run 5 iterations for each jitter value
- Save results to `reliability_jitter.csv`

**Expected duration:** ~5-10 minutes

### Step 4: Plot Results

After experiments complete, generate plots:

```bash
# Plot loss experiment results
python3 plot_results.py loss

# Plot jitter experiment results
python3 plot_results.py jitter
```

This will:
- Generate PNG plots with 90% confidence intervals
- Display statistics table in terminal
- Verify data integrity (MD5 hash check)
- Save plots as `loss_experiment.png` and `jitter_experiment.png`

## Understanding the Results

### CSV File Format
Both CSV files contain:
- `iteration`: Iteration number (0-4)
- `loss`: Packet loss percentage
- `delay`: Base delay in ms
- `jitter`: Delay jitter in ms
- `md5_hash`: MD5 hash of received file
- `ttc`: Time to complete transfer (seconds)

### What to Look For

#### Loss Experiment
- **Expected behavior**: Download time should increase as packet loss increases
- **Why**: More retransmissions needed, timeouts occur more frequently
- **Key metrics**: 
  - How much does time increase per 1% loss?
  - Does the protocol handle 5% loss without failures?
  - Are all MD5 hashes identical (reliable transfer)?

#### Jitter Experiment
- **Expected behavior**: Download time may increase with higher jitter
- **Why**: Variable delays affect RTT estimation and timeout calculations
- **Key metrics**:
  - How does RTO adaptation handle jitter?
  - Is performance stable across iterations?
  - Does high jitter cause spurious retransmissions?

### Confidence Intervals
- **90% CI** shows variability in measurements
- Narrow CI = consistent performance
- Wide CI = high variability, protocol may be sensitive to network conditions

## Troubleshooting

### If Mininet experiments fail:
```bash
# Clean up Mininet
sudo mn -c

# Check if Ryu controller is running
ps aux | grep ryu

# Restart Ryu controller
ryu-manager ryu.app.simple_switch_13
```

### If plots don't generate:
```bash
# Verify CSV files exist
ls -lh reliability_*.csv

# Check first few lines of CSV
head reliability_loss.csv
```

### If transfer fails (different MD5 hashes):
- Check server/client implementation
- Increase timeout values
- Reduce window size (SWS parameter in p1_exp.py)

## Modifying Experiments

### Change Window Size
Edit `p1_exp.py` line 57:
```python
SWS = 5 * 1180  # Change multiplier (e.g., 10 * 1180 for larger window)
```

### Change Loss/Jitter Ranges
Edit `p1_exp.py` lines 63-71:
```python
if expname == "loss":
    loss_list = [1, 2, 3, 4, 5]  # Modify these values
    delay_list = [20]
    jitter_list = [0]
elif expname == "jitter":
    delay_list = [20]
    loss_list = [1]
    jitter_list = [20, 40, 60, 80, 100]  # Modify these values
```

### Change Number of Iterations
Edit `p1_exp.py` line 60:
```python
NUM_ITERATIONS = 5  # Increase for more statistical confidence
```

## Expected Output

### Terminal Output (During Experiment)
```
--- Running topology with 1% packet loss, base delay 20ms and jitter 0ms (iter 1/5)
Starting file transfer: 6291456 bytes
Transfer complete: 6291456 bytes in 8.45s (0.71 MB/s)
...
```

### Plot Statistics Output
```
=== Loss Experiment Statistics ===
Loss Rate (%)   Mean Time (s)   90% CI (±)      Min (s)     Max (s)    
---------------------------------------------------------------------------
1               8.234           0.156           8.102       8.421      
2               9.567           0.234           9.287       9.845      
...
```

## Report Writing Tips

### What to Include:

1. **Methodology**
   - Topology description (h1-s1-h2)
   - Parameter ranges tested
   - Number of iterations

2. **Results**
   - Include both plots
   - Reference confidence intervals
   - Note any anomalies

3. **Analysis**
   - Explain trends observed
   - Relate to protocol mechanisms (RTO, retransmission, SACK)
   - Compare loss vs jitter impact

4. **Sample Observations**
   - "As packet loss increases from 1% to 5%, download time increases by approximately X%, demonstrating the protocol's ability to recover from losses through retransmission."
   - "Delay jitter has a moderate impact on performance, with Y% increase from 20ms to 100ms jitter, suggesting the RTO adaptation mechanism effectively handles variable delays."
   - "All transfers completed with identical MD5 hashes, confirming 100% reliability across all network conditions tested."

## Quick Reference Commands

```bash
# Complete workflow:
# Terminal 1: Start controller
ryu-manager ryu.app.simple_switch_13

# Terminal 2: Run experiments
cd "/home/aditya12/COL334-Assignments/Assignment 4/part1"
sudo python3 p1_exp.py loss
sudo python3 p1_exp.py jitter

# Generate plots
python3 plot_results.py loss
python3 plot_results.py jitter

# Clean up
sudo mn -c
```

## Contact/Issues
- Verify Ryu controller is running before starting experiments
- Each experiment takes several minutes - be patient
- If stuck, run `sudo mn -c` to clean up Mininet state
