#!/bin/bash
if [ -f .aios_daemon.pid ]; then
    PID=
    kill -15 12244
    rm .aios_daemon.pid
    echo "AIOS Daemon gracefully stopped"
else
    echo "Daemon PID file not found"
fi
