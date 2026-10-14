"""Small pretrained MobileNetV3 encoder + lightweight refinement decoder.

A valid official ImageNet checkpoint is mandatory for real training. Random
architecture construction is exposed only for synthetic shape/initialization tests.
"""
import hashlib
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
from torchvision.models import mobilenet_v3_small

IMAGENET_URL='https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth'


def block(cin,cout):
    return nn.Sequential(nn.Conv2d(cin,cout,3,padding=1,bias=False),nn.GroupNorm(4,cout),nn.SiLU(),nn.Conv2d(cout,cout,3,padding=1,bias=False),nn.GroupNorm(4,cout),nn.SiLU())


class PadRefinement(nn.Module):
    def __init__(self,backbone):
        super().__init__();self.encoder=backbone.features;old=self.encoder[0][0]
        new=nn.Conv2d(4,old.out_channels,old.kernel_size,stride=old.stride,padding=old.padding,bias=False)
        with torch.no_grad():new.weight.zero_();new.weight[:,:3].copy_(old.weight)
        self.encoder[0][0]=new
        for p in self.encoder.parameters():p.requires_grad=False
        # Only the input convolution adapts the coarse channel; all other
        # pretrained encoder layers are frozen for this ten-source protocol.
        new.weight.requires_grad=True
        self.reduce=nn.Conv2d(576,96,1);self.decode=nn.ModuleList([block(96+48,64),block(64+24,48),block(48+16,32),block(32+16,16)]);self.head=nn.Sequential(block(17,16),nn.Conv2d(16,1,1))
    def train(self,mode=True):
        super().train(mode);self.encoder.eval();return self
    def forward(self,x):
        size=x.shape[-2:];features=[];z=x
        for i,layer in enumerate(self.encoder):
            z=layer(z)
            if i in [0,1,3,8,12]:features.append(z)
        z=self.reduce(features[-1])
        for decode,skip in zip(self.decode,features[-2::-1]):z=decode(torch.cat([F.interpolate(z,size=skip.shape[-2:],mode='bilinear',align_corners=False),skip],1))
        z=F.interpolate(z,size=size,mode='bilinear',align_corners=False);return self.head(torch.cat([z,x[:,3:4]],1))


def build_pretrained(path):
    path=Path(path)
    if not path.is_file():raise FileNotFoundError('official ImageNet encoder checkpoint required; no random fallback')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if not digest.startswith('047dcff4'):raise ValueError('official torchvision checkpoint SHA prefix mismatch')
    encoder=mobilenet_v3_small(weights=None);encoder.load_state_dict(torch.load(path,map_location='cpu',weights_only=True),strict=True)
    return PadRefinement(encoder),digest


def synthetic_test_model():
    """Never save/train/evaluate this random architecture on private samples."""
    return PadRefinement(mobilenet_v3_small(weights=None))


def bce_dice(logits,target):
    probability=logits.sigmoid();intersection=(probability*target).sum((1,2,3));denominator=probability.sum((1,2,3))+target.sum((1,2,3))
    return F.binary_cross_entropy_with_logits(logits,target)+(1-(2*intersection+1)/(denominator+1)).mean()
