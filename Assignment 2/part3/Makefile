# Makefile for Part 3

.PHONY: plot run clean


# The 'plot' target first ensures the results are generated, then creates the plot.
plot: part3_results.csv
	sudo python3 run_experiments.py
	python3 plot_results.py

# This rule defines how to create the results file by running the experiment script.
part3_results.csv:
	sudo python3 runner.py

# The 'run' target executes the experiment without creating a plot.
run-fcfs:
	sudo python3 runner.py

# The 'clean' target removes all generated files and directories.
clean:
	rm -f part3_results.csv p3_plot.png
	rm -rf logs __pycache__