import matplotlib.pyplot as plt
import csv
import sys
import os

default_csv = 'part3_results.csv'
default_plot = 'p3_plot.png'

def plot_results(csv_file=default_csv, plot_file=default_plot):
   

    if not os.path.exists(csv_file):
        print(f"Error: CSV file not found at '{csv_file}'")
        return

    c_values = []
    jfi_values = []

    try:
        with open(csv_file, mode='r', newline='') as infile:
            reader = csv.reader(infile)
            
          
            header = next(reader)
            
            c_col_index = -1
            jfi_col_index = -1
            
            for i, col_name in enumerate(header):
                if col_name.lower() == 'c_value':
                    c_col_index = i
                elif 'jfi' in col_name.lower() or 'fairness' in col_name.lower():
                    jfi_col_index = i
            
            if c_col_index == -1 or jfi_col_index == -1:
                print("Error: CSV must contain columns for 'c' and 'JFI'.")
                print(f"Found columns: {header}")
                return

            for row in reader:
                if row: 
                    c_values.append(int(row[c_col_index]))
                    jfi_values.append(float(row[jfi_col_index]))

    except (IOError, StopIteration) as e:
        print(f"Error reading CSV file: {e}")
        return
    except ValueError as e:
        print(f"Error converting data to number: {e}. Please check CSV data format.")
        return

    if not c_values:
        print("CSV file is empty or contains no data rows.")
        return

    plt.figure(figsize=(8, 5))
    plt.plot(c_values, jfi_values, marker='o', linestyle='-')
    
    plt.xlabel('Number of Back-to-Back Requests by Greedy Client (c)')
    plt.ylabel("Jain's Fairness Index (JFI)")
    plt.title("JFI vs c")
    plt.grid(True)
    
    plt.xticks(c_values)
    plt.ylim(0, 1.1)
    
    plt.tight_layout()

   
    output_plot = 'p3_plot.png'
    
    output_dir = os.path.dirname(output_plot)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    plt.savefig(output_plot)
    print(f"Plot saved to {output_plot}")


if __name__ == "__main__":

    csv_input_file = sys.argv[1] if len(sys.argv) > 1 else default_csv
    
    
    plot_results(csv_input_file, 'p3_plot.png')