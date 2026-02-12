import torch
import torch.nn as nn
import torch.nn.functional as F

class FeatureRegressor(nn.Module):
    def __init__(self, student_channels, teacher_channels):
        super(FeatureRegressor, self).__init__()
        self.regressors = nn.ModuleList()
        for s_ch, t_ch in zip(student_channels, teacher_channels):
            self.regressors.append(
                nn.Conv2d(s_ch, t_ch, kernel_size=1, stride=1, padding=0, bias=False)
            )

    def forward(self, student_features):
        regressed_features = []
        for i, feat in enumerate(student_features):
            regressed_features.append(self.regressors[i](feat))
        return regressed_features

class KDLoss(nn.Module):
    def __init__(self, weights=[1.0, 1.0, 1.0, 1.0]):
        super(KDLoss, self).__init__()
        self.weights = weights
        self.criterion = nn.MSELoss()

    def forward(self, student_features, teacher_features):
        loss = 0
        for i, (s_feat, t_feat) in enumerate(zip(student_features, teacher_features)):
            if s_feat.shape != t_feat.shape:
                 s_feat = F.interpolate(s_feat, size=t_feat.shape[2:], mode='bilinear', align_corners=False)
            
            branch_loss = self.criterion(s_feat, t_feat)
            loss += self.weights[i] * branch_loss
        return loss


class DistillerWrapper(nn.Module):
    def __init__(self, student, teacher, regressor, distill_option='all'):
        super(DistillerWrapper, self).__init__()
        self.student = student
        self.teacher = teacher
        self.regressor = regressor
        self.distill_option = distill_option
        
        # Freeze Teacher
        for param in self.teacher.parameters():
            param.requires_grad = False
        self.teacher.eval()

    def forward(self, x, embedding, gt=None):
        # Student Forward
        # OneRestore forward_features 리턴: [x_l, x_m, x_s, x_out]
        # x_l (32), x_m (64), x_s (128), x_out (32)
        # OneRestore에서 forward_features 호출 시 DataParallel로 래핑되어 있음
        if isinstance(self.student, nn.DataParallel) or isinstance(self.student, nn.parallel.DistributedDataParallel):
             student_feats = self.student.module.forward_features(x, embedding)
        else:
             student_feats = self.student.forward_features(x, embedding)
          
        # Teacher Forward
        with torch.no_grad():
            # BioIR forward_features 리턴: [level1, level2, level3, dec_level1]
            # level1 (48), level2 (96? dim*2), level3 (192? dim*4), dec_level1 (48)
            teacher_feats = self.teacher.forward_features(x)

        # 옵션 기반 feature 필터링  
        if self.distill_option == 'decoder':
            # 마지막 디코더 출력만 사용
            student_feats = [student_feats[-1]]
            teacher_feats = [teacher_feats[-1]]

        # Regress Student Features
        regressed_s_feats = self.regressor(student_feats)

        return regressed_s_feats, teacher_feats
