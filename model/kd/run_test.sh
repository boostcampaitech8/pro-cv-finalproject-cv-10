#!/bin/bash

# Config
# KD 적용한 Student 체크포인트 경로
RESTORE_MODEL="./ckpts/KD_Result_15ep_scrutinize_add_smd/KD_OneRestore_ep5_loss0.0857_weights.tar" 
#"./ckpts/KD_Result_15ep_scrutinize/KD_OneRestore_ep5_loss0.0884_weights.tar"
# Embedder 경로 - 필수
EMBEDDER_PATH="/data/ephemeral/home/KD/OneRestore/ckpts/embedder_model_onlysingapor_1.tar"

# 테스트할 이미지, 결과 경로
INPUT_DIR="./demo_images/"
OUTPUT_DIR="./results_scr_2/results_5ep/"

# 텍스트 프롬프트 - 'haze', 'rain', 'snow', 'low', 'clear' ...
PROMPT=""

CMD="python ./OneRestore/test.py \
    --restore-model-path \"$RESTORE_MODEL\" \
    --embedder-model-path \"$EMBEDDER_PATH\" \
    --input \"$INPUT_DIR\" \
    --output \"$OUTPUT_DIR\""

if [ -n "$PROMPT" ]; then
    CMD="$CMD --prompt \"$PROMPT\""
fi

echo "Starting Test..."
echo "$CMD"
eval $CMD
