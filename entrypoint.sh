#!/bin/bash

set -e
gunicorn app:app -b 0.0.0.0:8000 --workers 4 --capture-output --log-level=debug
