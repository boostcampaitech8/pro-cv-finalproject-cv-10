import os
import time
import torch
import torch.nn as nn
import argparse
from torch.utils.data import DataLoader
from torchvision import transforms
import sys
import wandb

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'OneRestore'))
sys.path.append(os.path.join(current_dir, 'BioIR', 'All_in_One'))

from OneRestore.utils.utils import print_args, load_restore_ckpt_with_optim, load_embedder_ckpt, adjust_learning_rate, tensor_metric, save_checkpoint, load_restore_ckpt, AverageMeter
from OneRestore.model.loss import Total_loss
from OneRestore.folder_dataset import KD_FolderDataset
from OneRestore.model.OneRestore import OneRestore

from net.model import BioIR
from distiller import FeatureRegressor, KDLoss, DistillerWrapper

# Transforms 정의
transform_resize = transforms.Compose([
    transforms.Resize([224, 224]),
    transforms.ToTensor()
])

def load_bioir_teacher(ckpt_path, device):
    print(f'> Loading BioIR Teacher from {ckpt_path}...')
    # BioIR config
    model = BioIR(dim=48, num_blocks=[6,6,14], num_refinement_blocks=4, ffn_expansion_factor=3)
    
    if ckpt_path and os.path.exists(ckpt_path):
        checkpoint = torch.load(ckpt_path, map_location=device)
        # state_dict 래핑 관련 처리
        if 'state_dict' in checkpoint:
            state_dict = checkpoint['state_dict']
        else:
            state_dict = checkpoint
            
        # 필요 시 key 수정 (예: 'net.' 제거)
        new_state_dict = {}
        for k, v in state_dict.items():
            if k.startswith('net.'):
                new_state_dict[k[4:]] = v
            else:
                new_state_dict[k] = v
        
        try:
            model.load_state_dict(new_state_dict)
            print("BioIR Teacher weights loaded successfully.")
        except Exception as e:
            print(f"Error loading BioIR weights: {e}")
            print("Proceeding with random weights for debugging (WARNING: Do not use for actual training without fix)")
    else:
        print(f"Warning: Checkpoint {ckpt_path} not found. Using random weights.")

    model.to(device)
    model.eval()
    return model

def main(args):
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f'> Training on {device}')

    # Student 로드 (OneRestore)
    print('> Initializing Student (OneRestore)...')
    
    embedder = load_embedder_ckpt(device, freeze_model=True, ckpt_name=args.embedder_model_path)
    
    
    # 체크포인트 로더 'Resume' (전체 ckpt) / 'Finetune' (가중치만)
    # load_restore_ckpt_with_optim 대체
    print(f'> Loading Student from {args.restore_model_path}...')
    model = OneRestore().to(device)
    
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    cur_epoch = 0
    
    if args.restore_model_path and os.path.exists(args.restore_model_path):
        if torch.cuda.is_available():
            checkpoint = torch.load(args.restore_model_path)
        else:
            checkpoint = torch.load(args.restore_model_path, map_location=torch.device('cpu'))
            
        # 전체 Checkpoint (Resume)
        if isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
            print("  - Detected Full Checkpoint (Resume Mode)")
            state_dict = checkpoint['state_dict']
            
            # 'module.' 존재 시 제거
            new_state_dict = {}
            for k, v in state_dict.items():
                name = k[7:] if k.startswith('module.') else k
                new_state_dict[name] = v
            model.load_state_dict(new_state_dict)
            
            if 'optimizer' in checkpoint:
                optimizer.load_state_dict(checkpoint['optimizer'])
            if 'epoch' in checkpoint:
                cur_epoch = checkpoint['epoch']
                
        # 가중치만
        else:
            print("  - Detected Weights-Only Checkpoint (Finetune Mode)")
            state_dict = checkpoint
            # 'module.' 존재 시 제거
            new_state_dict = {}
            for k, v in state_dict.items():
                name = k[7:] if k.startswith('module.') else k
                new_state_dict[name] = v
            model.load_state_dict(new_state_dict)
            # 파인튜닝을 위한 epoch 리셋
            cur_epoch = 0
            
    else:
        print("  - No pretrained path provided or file not found. Initializing from scratch.")

    # Wrap in DataParallel if multiple GPUs
    if torch.cuda.device_count() > 1:
        model = nn.DataParallel(model)
        
    student = model
    
    # Teacher 로드 (BioIR)
    teacher = load_bioir_teacher(args.teacher_ckpt_path, device)

    # WandB Init
    wandb.init(project=args.wandb_project, entity=args.wandb_entity, name=args.wandb_name, config=args)


    # Distiller 설정
    # 'decoder' - 마지막 디코더 출력 feature만 증류
    if args.distill_option == 'decoder':
        # L1 Decoder : 마지막 출력만
        # Student: [32, 64, 128, 32] -> [32]
        # Teacher: [48, 96, 192, 48] -> [48]
        student_channels = [32]
        teacher_channels = [48]
        print("> Distillation Option: Decoder-Only (Connecting Final Decoder Output)")
    else:
        # All (Encoder L1~L3 + Decoder L1)
        student_channels = [32, 64, 128, 32]
        teacher_channels = [48, 96, 192, 48]
        print("> Distillation Option: All (Multi-scale Feature Matching)")
    
    regressor = FeatureRegressor(student_channels, teacher_channels).to(device)
    
    optimizer.add_param_group({'params': regressor.parameters()})
    
    distiller = DistillerWrapper(student, teacher, regressor, distill_option=args.distill_option).to(device)
    kd_criterion = KDLoss(weights=args.kd_weights).to(device)
    
    # Task Loss
    task_criterion = Total_loss(args)

    print('> Loading dataset from folders...')
    train_root = os.path.join(args.train_input, 'Train') # 'Train' 폴더 경로
    if not os.path.exists(train_root):
        train_root = args.train_input

    data = KD_FolderDataset(train_root, patch_size=224, tasks=['Dehaze'])#, 'Derain'])
    dataset = DataLoader(dataset=data, num_workers=args.num_works, batch_size=args.bs, shuffle=True)

    print('> Start KD training...')
    start_all = time.time()
    
    best_loss = float('inf')

    for epoch in range(cur_epoch, args.epoch):
        optimizer = adjust_learning_rate(optimizer, epoch, args.adjust_lr)
        learnrate = optimizer.param_groups[0]['lr']
        student.train()
        regressor.train()
        
        # 누적 평균 계산(OneRestore utils -> AverageMeter 활용)
        loss_total_m = AverageMeter()
        loss_task_m = AverageMeter()
        loss_kd_m = AverageMeter()
        mse_m = AverageMeter()
        psnr_m = AverageMeter()
        
        for i, (pos, degraded_img, degraded_type) in enumerate(dataset, 0):
            # pos: GT, degraded_img: Input, degraded_type: list of strings (prompts)
            
            pos = pos.to(device)
            degraded_img = degraded_img.to(device)
            # degraded_type: 데이터로더에서 온 튜플/리스트
            # e.g. ("haze", "haze", "rain", "rain")
            
            # Forward Embedder
            text_embedding, _, _ = embedder(list(degraded_type), 'text_encoder')
            
            # --- Forward Pass ---
            # Student Task 출력
            student_out = student(degraded_img, text_embedding)
            
            # 증류 features
            regressed_s_feats, teacher_feats = distiller(degraded_img, text_embedding)
            
            # --- loss 계산 ---
            # Task Loss
            # inp for Total_loss: [텐서, 타입 리스트]
            inp_for_loss = [degraded_img, list(degraded_type)]
            
            neg = torch.zeros(degraded_img.size(0), 0, degraded_img.size(1), degraded_img.size(2), degraded_img.size(3)).to(device)
            loss_task = task_criterion(inp_for_loss, pos, neg, student_out)
            
            # KD Loss (Feature Matching)
            loss_kd = kd_criterion(regressed_s_feats, teacher_feats)
            
            # Total Loss
            total_loss = loss_task + (args.kd_lambda * loss_kd)
            
            optimizer.zero_grad()
            total_loss.backward()
            optimizer.step()
            
            # 현재 배치 상 metric 계산
            mse = tensor_metric(pos, student_out, 'MSE', data_range=1)
            psnr = tensor_metric(pos, student_out, 'PSNR', data_range=1)

            # 누적 평균 계산
            loss_total_m.update(total_loss.item(), degraded_img.size(0))
            loss_task_m.update(loss_task.item(), degraded_img.size(0))
            loss_kd_m.update(loss_kd.item(), degraded_img.size(0))
            mse_m.update(mse, degraded_img.size(0))
            psnr_m.update(psnr, degraded_img.size(0))
            
            # 콘솔 로깅 (100 iter마다)
            if i % 100 == 0:
                print(f"[Epoch {epoch+1}][{i}/{len(dataset)}] lr:{learnrate:.6f} "
                      f"Total:{total_loss.item():.4f} Task:{loss_task.item():.4f} KD:{loss_kd.item():.4f} "
                      f"PSNR:{psnr:.4f}")
        
        # wandb 로깅 -> 에폭 평균
        wandb.log({
            "Epoch": epoch + 1,
            "Total Loss": loss_total_m.avg,
            "Task Loss": loss_task_m.avg,
            "KD Loss": loss_kd_m.avg,
            "MSE": mse_m.avg,
            "PSNR": psnr_m.avg,
            "Learning Rate": learnrate
        })
        print(f"==> Epoch {epoch+1} Complete. Avg Loss: {loss_total_m.avg:.4f} Avg PSNR: {psnr_m.avg:.4f}")

        # ============================ 체크포인트 저장 ============================
        
        # 'module.' prefix 제거
        def get_stripped_state_dict(model):
            state_dict = model.state_dict()
            new_state_dict = {}
            for k, v in state_dict.items():
                if k.startswith('module.'):
                    new_state_dict[k[7:]] = v
                else:
                    new_state_dict[k] = v
            return new_state_dict
        # ---------------------------------------------------------------------------
        #  매 에폭 저장용 수정 0205nbc8
        # ---------------------------------------------------------------------------
        # 매 에폭 Checkpoint Saving (Every Epoch)
        ckpt_name = f'KD_OneRestore_ep{epoch+1}_loss{loss_total_m.avg:.4f}'
        
        # resume용 Full Checkpoint
        save_path_full = os.path.join(args.save_model_path, f'{ckpt_name}.tar')
        torch.save({
            'epoch': epoch + 1,
            'state_dict': student.state_dict(),
            'optimizer': optimizer.state_dict(),
            'regressor': regressor.state_dict(),
            'loss': loss_total_m.avg  # Use epoch average loss
        }, save_path_full)
        
        # Test용 only Weights
        save_path_weights = os.path.join(args.save_model_path, f'{ckpt_name}_weights.tar')
        torch.save(get_stripped_state_dict(student), save_path_weights)
        
        print(f"  [Saved Epoch {epoch+1}] {save_path_full}")


        # ---------------------------------------------------------------------------
        # =======================================================================
    end_all = time.time()
    print(f'Whole Training Time: {end_all-start_all:.2f}s')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="OneRestore KD Training")
    
    # 경로
    parser.add_argument("--embedder-model-path", type=str, default="./OneRestore/ckpts/embedder_model.tar")
    parser.add_argument("--restore-model-path", type=str, default=None, help="Student Pretrained Path")
    parser.add_argument("--teacher-ckpt-path", type=str, required=True, help="BioIR Teacher Checkpoint Path (.ckpt)")
    parser.add_argument("--train-input", type=str, default="/data/ephemeral/home/BioIR/All_in_One/data", help="Root Data Directory")
    parser.add_argument("--save-model-path", type=str, default="./ckpts/KD_Result/")
    
    # 학습 관련 파라미터
    parser.add_argument("--epoch", type=int, default=15)
    parser.add_argument("--bs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--adjust-lr", type=int, default=40)
    parser.add_argument("--num-works", type=int, default=4)
    
    # 손실 관련 파라미터
    parser.add_argument("--loss-weight", nargs='+', type=float, default=(0.6, 0.3, 0.1)) # For Task Loss
    parser.add_argument("--kd-lambda", type=float, default=1.0, help="Weight for KD Loss")
    parser.add_argument("--kd-weights", nargs='+', type=float, default=(1.0, 1.0, 1.0, 1.0), help="Weights for encoding levels 1,2,3 and decoder")
    parser.add_argument("--distill-option", type=str, default='all', choices=['all', 'decoder'], help="Distillation strategy: 'all' (multi-scale) or 'decoder' (final feature only)")
    
    parser.add_argument("--degr-type", nargs='+', default=['clear', 'low', 'haze', 'rain', 'snow',
        'low_haze', 'low_rain', 'low_snow', 'haze_rain', 'haze_snow', 'low_haze_rain', 'low_haze_snow'])

    # Tools
    parser.add_argument("--wandb-project", type=str, default="Feature_KD_BioIR_OneRestore", help="WandB Project Name")
    parser.add_argument("--wandb-entity", type=str, default=None, help="WandB Entity (Account/Team)")
    parser.add_argument("--wandb-name", type=str, default="15epoch_0205", help="WandB Run Name")

    args = parser.parse_args()
    
    os.makedirs(args.save_model_path, exist_ok=True)
    
    print_args(args)
    main(args)
