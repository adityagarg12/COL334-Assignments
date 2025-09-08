# Makefile for Part 4 - Round-Robin Scheduling Experiment

.PHONY: all run-rr plot clean

# Default target
all: plot

# Runs the full experiment for c=1 to 10 and generates the results CSV.
run-rr:
	sudo python3 runner.py

# The 'plot' target depends on the results file being created first.
# It runs the experiment and then immediately creates the plot.
plot: part4_results.csv
	sudo python3 run_experiments.py
	python3 plot_results.py

# This rule tells 'make' how to create the results file.
part4_results.csv: runner.py client.py server.py topology.py
	sudo python3 runner.py

# Clean up generated files
clean:
	rm -f part4_results.csv p4_plot.png
	rm -rf logs __pycache__
