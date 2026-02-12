#!/bin/bash

# distillation Config
# Teacher (BioIR) Path - 필수
BIOIR_CKPT="/data/ephemeral/home/BioIR/All_in_One/ckpt/Dehaze_plus/epoch=7-val_psnr=23.78_02031836.ckpt"

# 데이터셋 root 경로 - 필수 ('Train/Dehaze', 'Train/Derain' 등 포함하도록 설정)
DATA_ROOT="/data/ephemeral/home/BioIR/All_in_One/data_2"

# OneRestore Embedder 경로 - 필수
EMBEDDER_PATH="/data/ephemeral/home/KD/OneRestore/ckpts/embedder_model_onlysingapor_1.tar"

# Student (OneRestore) 사전 학습 가중치 - 선택
RESTORE_CKPT="/data/ephemeral/home/KD/OneRestore/ckpts/onerestore_cdd-11.tar"

# WandB 설정
WANDB_PROJECT="Feature_KD_BioIR_OneRestore"
WANDB_ENTITY=""

# None: L1~L3 인코더 + L1 디코더 feature에 대해 distillation 진행 / 'decoder': L1 디코더에 대해서만 distillation 진행
DISTILL_OPTION="decoder"

# 출력디렉터리
SAVE_DIR="./ckpts/KD_Result_15ep_scrutinize_add_smd/"

# 빌드 명령어
CMD="python train_kd_OneRestore.py \
    --teacher-ckpt-path \"$BIOIR_CKPT\" \
    --train-input \"$DATA_ROOT\" \
    --embedder-model-path \"$EMBEDDER_PATH\" \
    --bs 8 \
    --lr 0.0002 \
    --epoch 15 \
    --save-model-path \"$SAVE_DIR\" \
    --wandb-project \"$WANDB_PROJECT\" \
    --distill-option \"$DISTILL_OPTION\""

# WandB Entity 설정
if [ -n "$WANDB_ENTITY" ]; then
    CMD="$CMD --wandb-entity \"$WANDB_ENTITY\""
fi

# 이어서 학습
if [ -n "$RESTORE_CKPT" ]; then
    CMD="$CMD --restore-model-path \"$RESTORE_CKPT\""
fi

# 실행
echo "Starting Training..."
echo "Option: $DISTILL_OPTION"
echo "$CMD"
eval $CMD
