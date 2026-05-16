#!/bin/bash
gunicorn --bind 127.0.0.1:14080 main:app
