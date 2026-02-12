# Knowledge Distillation

이미지 복원 파트의 On-device 추론 성능 향상을 위해 BioIR 모델로부터 OneRestore 모델로의 feature 기반 지식 증류를 적용하였다.

## Folder Structure
```
model
├─ kd
│  ├── convert_ckpt.py  # 추론용 체크포인트로 변환
│  ├── distiller.py  # 증류를 위한 loss, wrapper, regressor
│  ├── train_kd_OneRestore.py  # 증류 train
│  ├── run_kd.sh  # 증류 train 진행 스크립트
│  └── run_test.sh  # 증류가 적용된 모델 체크포인트 테스트 스크립트
├─ ...
```

## Framework
- 각 모델의 L1~L3 Encoder 및 L1 Decoder 출력 feature에 대한 1:1 매핑 적용
- regressor를 통해 feature 채널을 align해 계산한 MSE 기반 distillation
loss 사용
- Teacher와 Embedder는 freeze하고, kd loss와 OneRestore의 task loss를 기반으로 Student에 이어서 학습 진행