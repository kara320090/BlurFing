"""Versioned local-detail plus frozen whole-body context development model."""
import copy
import hashlib
import io
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F
from torchvision.models import mobilenet_v3_small
from pad_refinement_model import PadRefinement, block, IMAGENET_SHA256
from pad_refinement_data_contract_v2 import checked_bytes

STAGES = {3: (24, 8), 8: (48, 16), 12: (576, 32)}
CONTEXT_CHANNELS = 648


def encoder_identity(encoder):
    h = hashlib.sha256()
    for name, value in sorted(encoder.state_dict().items()):
        h.update(name.encode()); h.update(str(value.dtype).encode())
        h.update(str(tuple(value.shape)).encode()); h.update(value.cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def align_stage(value, stride):
    """Anchor all stages at input-edge 0.5 + 8*i; border extension is explicit.

    These are convolution lattice anchors, not claims of point-local receptive
    fields: SE and deep convolution intentionally carry global image context.
    """
    if value.ndim != 4 or value.shape[-2:] != (256//stride, 256//stride):
        raise ValueError('context_feature_lattice_shape')
    index = torch.arange(32, device=value.device, dtype=value.dtype) * (8/stride)
    norm = 2*(index+.5)/value.shape[-1]-1
    yy, xx = torch.meshgrid(norm, norm, indexing='ij')
    grid = torch.stack([xx, yy], -1)[None].expand(len(value), -1, -1, -1)
    return F.grid_sample(value, grid, mode='bilinear', padding_mode='border', align_corners=False)


class WholePadContext(PadRefinement):
    def __init__(self, backbone):
        # Clone BEFORE the parent replaces its RGB input convolution with 4ch.
        context_encoder = copy.deepcopy(backbone.features)
        super().__init__(backbone)
        self.context_encoder = context_encoder
        for parameter in self.context_encoder.parameters(): parameter.requires_grad = False
        self.context_projection = nn.Sequential(nn.Conv2d(CONTEXT_CHANNELS,16,1,bias=False),nn.GroupNorm(4,16),nn.SiLU())
        self.head = nn.Sequential(block(33,16),nn.Conv2d(16,1,1))
        self.context_encoder.eval()

    def train(self, mode=True):
        super().train(mode); self.context_encoder.eval(); return self

    def context_features(self, rgb):
        if rgb.ndim != 4 or rgb.shape[1:] != (3,256,256) or not torch.isfinite(rgb).all():
            raise ValueError('context_RGB_tensor_contract')
        self.context_encoder.eval(); z=rgb; features=[]
        with torch.no_grad():
            for index, layer in enumerate(self.context_encoder):
                z=layer(z)
                if index in STAGES:
                    channels, stride=STAGES[index]
                    if z.shape[1]!=channels: raise ValueError('context_encoder_stage_contract')
                    features.append(align_stage(z,stride))
        result=torch.cat(features,1)
        if result.shape[1:]!=(CONTEXT_CHANNELS,32,32) or not torch.isfinite(result).all():
            raise ValueError('context_encoder_output_contract')
        return result

    def sample_context(self, context, grid, valid):
        if context.ndim!=4 or context.shape[1:]!=(CONTEXT_CHANNELS,32,32): raise ValueError('context_cache_tensor_contract')
        if grid.shape!=(len(context),256,256,2) or valid.shape!=(len(context),1,256,256): raise ValueError('context_grid_shape')
        if not torch.isfinite(context).all() or not torch.isfinite(grid).all() or valid.dtype!=torch.bool:
            raise ValueError('context_grid_value_contract')
        projected=self.context_projection(context)
        sampled=F.grid_sample(projected,grid,mode='bilinear',padding_mode='border',align_corners=False)
        # Apply AFTER projection/sampling: learned affine/bias terms cannot
        # silently turn an invalid context location into a valid feature.
        return sampled*valid.to(sampled.dtype)

    def forward(self,x,context,grid,valid):
        if x.ndim!=4 or x.shape[1:]!=(4,256,256) or not torch.isfinite(x).all(): raise ValueError('context_local_input_contract')
        z=x; features=[]
        for index,layer in enumerate(self.encoder):
            z=layer(z)
            if index in [0,1,3,8,12]: features.append(z)
        z=self.reduce(features[-1])
        for decode,skip in zip(self.decode,features[-2::-1]):
            z=decode(torch.cat([F.interpolate(z,size=skip.shape[-2:],mode='bilinear',align_corners=False),skip],1))
        z=F.interpolate(z,size=(256,256),mode='bilinear',align_corners=False)
        return self.head(torch.cat([z,x[:,3:4],self.sample_context(context,grid,valid)],1))


def build_pretrained(path):
    data=checked_bytes(Path(path),IMAGENET_SHA256)
    backbone=mobilenet_v3_small(weights=None)
    backbone.load_state_dict(torch.load(io.BytesIO(data),map_location='cpu',weights_only=True),strict=True)
    return WholePadContext(backbone),IMAGENET_SHA256


def load_checkpoint(path,sha):
    from train_pad_refinement_tiles_v3 import finite_model
    data=checked_bytes(Path(path),sha); model=WholePadContext(mobilenet_v3_small(weights=None))
    model.load_state_dict(torch.load(io.BytesIO(data),map_location='cpu',weights_only=True),strict=True)
    finite_model(model); model.eval(); return model
