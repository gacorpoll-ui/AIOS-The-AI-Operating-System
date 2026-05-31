#!/bin/bash
if [ -f .aios_daemon.pid ]; then
    PID=
    if ps -p 12244 > /dev/null; then
        echo "AIOS Daemon is RUNNING (PID: 12244)"
    else
        echo "AIOS Daemon is DEAD (but PID file exists)"
    fi
else
    echo "AIOS Daemon is NOT RUNNING"
fi
