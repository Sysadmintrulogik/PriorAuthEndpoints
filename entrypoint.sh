#!/bin/bash

set -e
export PYTHONPATH=.
python3 ./app/kafka/consumer.py &
uvicorn application:app --host 0.0.0.0 --port 8000 --workers 4


#python3 application.py