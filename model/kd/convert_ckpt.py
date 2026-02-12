
import torch
import sys
import os

def convert_ckpt(ckpt_path):
    print(f"Processing {ckpt_path}...")
    if not os.path.exists(ckpt_path):
        print(f"Error: {ckpt_path} not found.")
        return

    checkpoint = torch.load(ckpt_path, map_location='cpu')
    
    # state_dict 추출
    if 'state_dict' in checkpoint:
        state_dict = checkpoint['state_dict']
    else:
        state_dict = checkpoint # key가 없는 경우 state_dict로 간주
        
    # module. 접두어 제거
    new_state_dict = {}
    for k, v in state_dict.items():
        if k.startswith('module.'):
            new_state_dict[k[7:]] = v
        else:
            new_state_dict[k] = v
            
    # 가중치 저장
    new_path = ckpt_path.replace('.tar', '_weights_converted.tar')
    torch.save(new_state_dict, new_path)
    print(f"Saved converted checkpoint to: {new_path}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python convert_ckpt.py <path_to_checkpoint.tar>")
    else:
        convert_ckpt(sys.argv[1])
