#!/bin/bash
#!/bin/bash
python ablation.py --dataset-name FetaTab --run-name a_ft
python ablation.py --dataset-name LongDocURL --run-name a_ldu
python ablation.py --dataset-name MMLongBench --run-name a_mlb
python ablation.py --dataset-name PaperTab --run-name a_ptb
python ablation.py --dataset-name PaperText --run-name a_ptx
