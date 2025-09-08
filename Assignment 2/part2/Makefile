.PHONY: all plot clean


RESULTS_CSV = output/results.csv
PLOT_PNG = output/p2_plot.png


all: $(PLOT_PNG)


plot: $(PLOT_PNG)


$(PLOT_PNG): $(RESULTS_CSV)
	python3 plot_results.py


$(RESULTS_CSV):
	sudo mn -c && sudo python3 runner.py


clean:
	rm -rf output
	sudo mn -c
