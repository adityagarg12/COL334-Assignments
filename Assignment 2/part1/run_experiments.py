
# STARTER CODE ONLY. EDIT AS DESIRED
#!/usr/bin/env python3
import re
import time
import csv
from pathlib import Path
from topo_wordcount import make_net

# Config
K_VALUES = [1, 2, 5, 10, 20, 50, 100]   
RUNS_PER_K = 5
SERVER_CMD = "./server --config config.json --quiet"
CLIENT_CMD_TMPL = "./client --config config.json --quiet"

RESULTS_CSV = Path("p1_results.csv")

def modify_config(key, value, config_path="config.json"):
   
    with open(config_path, "r") as f:
        content = f.read()
    
    trailing_newlines = ""
    match_trailing = re.search(r'(\n+)$', content)
    if match_trailing:
        trailing_newlines = match_trailing.group(1)
        content = content[: -len(trailing_newlines)]

    
    compact_match = re.match(r'\s*{.*}\s*$', content)
    if compact_match and "\n" not in content.strip():
       
        pattern = rf'("{key}"\s*:\s*)([^,}}]+)'
        new_content, count = re.subn(pattern, rf'\1{value}', content)
        if count == 0:
         
            new_content = re.sub(r'(})$', rf', "{key}": {value}\1', content)
        content = new_content
    else:
       
        lines = content.splitlines(keepends=True)
        new_lines = []
        key_found = False
        for line in lines:
            if re.match(rf'\s*"{key}"\s*:', line):
                indent = re.match(r'(\s*)', line).group(1)
                comma = "," if line.strip().endswith(",") else ""
                new_line = f'{indent}"{key}": {value}{comma}\n'
                new_lines.append(new_line)
                key_found = True
            else:
                new_lines.append(line)
        if not key_found:
            for i in range(len(new_lines)-1, -1, -1):
                if new_lines[i].strip() == "}":
                    indent = re.match(r'(\s*)', new_lines[i]).group(1)
                    new_lines.insert(i, f'{indent}"{key}": {value},\n')
                    break
        content = "".join(new_lines)

    with open(config_path, "w") as f:
        f.write(content.rstrip() + trailing_newlines)


def get_num_repetitions(config_path="config.json"):
    with open(config_path, "r") as f:
        content = f.read()
    m = re.search(r'"num_repetitions"\s*:\s*(\d+)', content)
    if m:
        return int(m.group(1))
    return None

num_reps = get_num_repetitions()
if num_reps is not None:
    RUNS_PER_K = num_reps

def main():
    # Prepare CSV
    if not RESULTS_CSV.exists():
        with RESULTS_CSV.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["k", "run", "elapsed_ms"])

    net = make_net()
    net.start()

    h1 = net.get('h1')  # client
    h2 = net.get('h2')  # server
   
    config_content = Path("config.json").read_text()
    m = re.search(r'"filename"\s*:\s*"([^"]+)"', config_content)
    input_filename = m.group(1) if m else None

    # Ensure input file exists (shared FS)
    if input_filename and not Path(input_filename).exists():
        Path(input_filename).write_text("cat,bat,cat,dog,dog,emu,emu,emu,ant\n")

    # # Start server
    # srv = h2.popen(SERVER_CMD, shell=True   , stdout=None, stderr=None)
    # time.sleep(0.5)  # give it a moment to bind

    try:
        for k in K_VALUES:
            for r in range(1, RUNS_PER_K + 1):
                modify_config("k", k) # should implement this function
                
                # Start server
                srv = h2.popen(SERVER_CMD, shell=True   , stdout=None, stderr=None)
                time.sleep(0.5)  # give it a moment to bind
                
                cmd = CLIENT_CMD_TMPL
                out = h1.cmd(cmd)
                print(out)
                time.sleep(1) 
                # parse ELAPSED_MS
                # m = re.search(r"ELAPSED_MS:(\d+)", out)
                m = re.search(r"ELAPSED_MS:(\d+(?:\.\d+)?)", out)
                if not m:
                    print(f"[warn] No ELAPSED_MS found for k={k} run={r}. Raw:\n{out}")
                    continue
                ms = float(m.group(1))
                with RESULTS_CSV.open("a", newline="") as f:
                    csv.writer(f).writerow([k, r, ms])
                print(f"k={k} run={r} elapsed_ms={ms}")
                
    finally:
        srv.terminate()
        time.sleep(0.2)
        net.stop()

if __name__ == "__main__":
    main()
