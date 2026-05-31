#!/bin/bash
# AIOS Daemon startup script
export PYTHONPATH="D:\aios\aios"
nohup python3 agent/core/daemon.py > /dev/null 2>&1 &
echo $! > .aios_daemon.pid
echo "AIOS Daemon started in background"
