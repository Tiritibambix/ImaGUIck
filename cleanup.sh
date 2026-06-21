#!/bin/bash

# WARNING: this script deletes ALL files in the uploads/ and output/ folders,
# regardless of age. For manual use only.
echo "WARNING: This will delete ALL files in uploads/ and output/ regardless of age."
echo "Press Ctrl+C within 5 seconds to cancel."
sleep 5

/usr/local/bin/python /app/cleanup.py --all
