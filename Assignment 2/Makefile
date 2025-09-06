SHELL := /bin/bash
VENV_DIR = venv
PIP = $(VENV_DIR)/bin/pip

# Runs one experiment with the FCFS server and parameters in config.json
run-fcfs:
	python3 runner.py

# Runs experiments for c=1..10 and generates the plot
plot:
	python3 plot_results.py

# Clean up results
clean:
	rm -rf part3_results/
	rm -f p3_plot.png