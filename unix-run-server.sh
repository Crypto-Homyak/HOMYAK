#!/bin/bash
gunicorn --workers 1 --threads 100 --bind 127.0.0.1:14080 main:app
