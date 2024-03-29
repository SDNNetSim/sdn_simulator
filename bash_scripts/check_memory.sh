#!/bin/bash

if [ "$#" -ne 1 ]; then
	echo "Usage: $0 <script_path>"
	exit 1
fi

script_path="$1"
script_name=$(basename "$script_path")

if [ ! -f "$script_path" ]; then
	echo "Error: $script_path is not a valid file path."
	exit 1
fi

ps u -p $(pgrep -d',' -f run_sim.py) | awk '{sum += $6} END {print "Total memory used is: " sum / 1024 " MB" " or " sum / 1024 / 1024 " GB"}'

num_proc=$(pgrep -fc "$script_name")
echo "Total number of processes used by $script_name is: $num_proc" 
