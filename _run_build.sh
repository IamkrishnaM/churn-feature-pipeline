#!/bin/bash
cd /home/krishnamadala/stack_ai/assignment_1
.venv/bin/python3 scripts/build_training_features.py --as-of 2026-03-31 > _build_log.txt 2>&1
echo "BUILD EXIT: $?" >> _build_log.txt
echo "Build done"