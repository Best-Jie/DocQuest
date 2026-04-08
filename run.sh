#!/bin/bash
python agents/ablation_agents.py --dataset-name MMLongBench --run-name gpt_ablation
python agents/ablation_agents.py --dataset-name PaperTab --run-name gpt_ablation
python agents/ablation_agents.py --dataset-name PaperText --run-name gpt_ablation