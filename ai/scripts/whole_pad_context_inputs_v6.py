"""GT-free context and pixel-center mapping; original encoded coordinates."""
import hashlib
import random
import numpy as np
import torch
from torchvision.transforms import functional as TF, InterpolationMode
from torch.utils.data import Dataset, DataLoader
from prepare_pad_refinement_data import letterbox
from pad_refinement_data_contract_v2 import read_source_rgb, load_crop
from train_whole_pad_target_v4 import PreparedInputs
import train_pad_refinement_tiles_v3 as common
from whole_pad_context_model_v6 import encoder_identity
from photo_resize_safety_v1 import MAX_ESTIMATED_WORKING_BYTES

CONTEXT_POLICY = dict(version='whole_body_RGB_context_v6',bbox='nonempty observed body union, min/max+1, no GT',
    coordinates='encoded original pixels; no EXIF transpose',resize='existing INTER_AREA letterbox 256; rounded axis sizes',
    encoder='official frozen RGB MobileNetV3-small, BN eval',stages=[3,8,12],
    lattice='input-edge anchor .5 + 8*i; coarse stages border-resampled to this lattice',
    sampling='bilinear border align_corners=False; validity after projection',
    augmentation='global identity; local RGB/coarse/label and inverse-coordinate field use same geometry',
    photometric='historical local-only augmentation; global RGB is fixed reference',GT_used=False)


def pixel_hash(value): return hashlib.sha256(value.tobytes()).hexdigest()


def grid_key(record): return (record['source_id'],tuple(record['bbox']))


def context_image(rgb,body):
    if rgb.shape!=body.shape+(3,) or rgb.dtype!=np.uint8 or body.dtype!=np.bool_ or not body.any():
        raise ValueError('nonempty_context_body_RGB_required')
    yy,xx=np.where(body); box=[int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1]
    a,b,c,d=box; small=body[b:d,a:c]
    image,_,_,geometry=letterbox(rgb[b:d,a:c],small,np.zeros_like(small))
    return image,dict(bbox=box,geometry=geometry,RGB_sha256=pixel_hash(image),body_pixel_sha256=pixel_hash(body))


def local_grid(record,context):
    a,b,c,d=record['bbox'];g=record['geometry'];A,B,C,D=context['bbox'];h=context['geometry']
    if (g['width'],g['height'])!=(c-a,d-b) or (h['width'],h['height'])!=(C-A,D-B): raise ValueError('context_bbox_geometry_mismatch')
    if not all(type(v) is int and v>0 for v in [g['scaled_width'],g['scaled_height'],h['scaled_width'],h['scaled_height']]):
        raise ValueError('context_nonzero_geometry_required')
    yy,xx=np.mgrid[:256,:256]; native_x=a+(xx+.5-g['left'])*(c-a)/g['scaled_width']
    native_y=b+(yy+.5-g['top'])*(d-b)/g['scaled_height']
    px=h['left']+(native_x-A)*h['scaled_width']/(C-A)
    py=h['top']+(native_y-B)*h['scaled_height']/(D-B)
    valid=((xx>=g['left'])&(xx<g['left']+g['scaled_width'])&(yy>=g['top'])&(yy<g['top']+g['scaled_height'])&
           (native_x>=A)&(native_x<C)&(native_y>=B)&(native_y<D))
    # Context feature index=(global input edge position-.5)/8, with 32 anchors.
    grid=np.stack([2*((px-.5)/8+.5)/32-1,2*((py-.5)/8+.5)/32-1],-1).astype(np.float32)
    grid[~valid]=0
    if not np.isfinite(grid).all(): raise ValueError('nonfinite_context_mapping')
    return grid,valid


def augment(rgb,coarse,label,grid,valid):
    """Preserve historical random draw order and local augmentation numerics."""
    field=torch.cat([grid.permute(2,0,1),valid.float()],0)
    k=random.randrange(4)
    rgb,coarse,label,field=[torch.rot90(t,k,[1,2]) for t in [rgb,coarse,label,field]]
    if random.random()<.5: rgb,coarse,label,field=[t.flip(2) for t in [rgb,coarse,label,field]]
    if random.random()<.5: rgb,coarse,label,field=[t.flip(1) for t in [rgb,coarse,label,field]]
    angle=random.uniform(-15,15);scale=random.uniform(.9,1.1)
    rgb=TF.affine(rgb,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.BILINEAR)
    coarse=TF.affine(coarse,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.NEAREST)
    label=TF.affine(label,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.NEAREST)
    field=TF.affine(field,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.BILINEAR)
    # Coverage uses a float32 roundoff bound, never an observed-image threshold.
    # Partially supported interpolation is excluded instead of borrowing a
    # zero-filled coordinate across a padding boundary.
    coverage=field[2:3];valid=coverage>=1-8*torch.finfo(torch.float32).eps
    grid=(field[:2]/coverage.clamp_min(torch.finfo(torch.float32).eps)).permute(1,2,0)
    grid=torch.where(valid.permute(1,2,0),grid,torch.zeros_like(grid))
    rgb=TF.adjust_brightness(rgb,random.uniform(.85,1.15));rgb=TF.adjust_contrast(rgb,random.uniform(.85,1.15))
    rgb=TF.adjust_saturation(rgb,random.uniform(.9,1.1))
    if random.random()<.15: rgb=TF.gaussian_blur(rgb,[3,3],[.5,.5])
    if random.random()<.15: rgb=(rgb+torch.randn_like(rgb)*.008).clamp(0,1)
    return rgb,coarse,label,grid,valid


class ContextInputs(PreparedInputs):
    def __init__(self,root,view,model):
        planned=sum(s['height']*s['width'] for s in view['sources'])+len(view['crops'])*256*256*14+len(view['sources'])*648*32*32*4
        if planned>MAX_ESTIMATED_WORKING_BYTES: raise ValueError('context_combined_cache_resource_limit')
        super().__init__(root,view)
        self.encoder_sha256=encoder_identity(model.context_encoder);self.context={};self.grids={};self.bindings={};self.grid_bindings={}
        if len(view['sources'])*648*32*32*4>256*1024*1024: raise ValueError('context_cache_resource_limit')
        for source in view['sources']:
            sid=source['source_id'];body,records,_=self.sources[sid]
            rgb=read_source_rgb(source['source_path'],source['source_sha256']);image,info=context_image(rgb,body)
            x=common.normalized_input(dict(rgb=image,coarse=np.zeros((256,256),np.uint8)))[:3]
            features=model.context_features(x[None])[0].cpu().numpy().copy();features.setflags(write=False)
            self.context[sid]=features;info.update(source_id=sid,source_sha256=source['source_sha256'],
                feature_sha256=pixel_hash(features),encoder_sha256=self.encoder_sha256,tiles=[])
            self.bindings[sid]=info
            for record in records:
                grid,valid=local_grid(record,info);grid.setflags(write=False);valid.setflags(write=False)
                key=grid_key(record)
                if key in self.grids: raise ValueError('duplicate_context_tile_bbox')
                self.grids[key]=(grid,valid)
                self.grid_bindings[key]=(pixel_hash(grid),pixel_hash(valid))
                info['tiles'].append(dict(bbox=record['bbox'],grid_sha256=pixel_hash(grid),valid_sha256=pixel_hash(valid)))

    def assert_unchanged(self,model=None):
        if model is not None and encoder_identity(model.context_encoder)!=self.encoder_sha256: raise ValueError('context_encoder_cache_mismatch')
        for sid,features in self.context.items():
            if pixel_hash(features)!=self.bindings[sid]['feature_sha256']: raise ValueError('context_feature_cache_changed')
        for key,(grid,valid) in self.grids.items():
            if (pixel_hash(grid),pixel_hash(valid))!=self.grid_bindings[key]: raise ValueError('context_grid_cache_changed')

    def predict(self,model,sid):
        if encoder_identity(model.context_encoder)!=self.encoder_sha256: raise ValueError('context_encoder_cache_mismatch')
        if pixel_hash(self.context[sid])!=self.bindings[sid]['feature_sha256']: raise ValueError('context_feature_cache_changed')
        body,records,arrays=self.sources[sid];values=[];model.eval()
        with torch.no_grad():
            for start in range(0,len(records),common.PROTOCOL['batch_size']):
                batch=arrays[start:start+common.PROTOCOL['batch_size']];selected=records[start:start+len(batch)]
                for record in selected:
                    key=grid_key(record);grid,valid=self.grids[key]
                    if (pixel_hash(grid),pixel_hash(valid))!=self.grid_bindings[key]: raise ValueError('context_grid_cache_changed')
                x=torch.stack([common.normalized_input({k:v.copy() for k,v in a.items()}) for a in batch])
                c=torch.from_numpy(self.context[sid].copy())[None].expand(len(x),-1,-1,-1)
                grids=torch.stack([torch.from_numpy(self.grids[grid_key(r)][0].copy()) for r in selected])
                valid=torch.stack([torch.from_numpy(self.grids[grid_key(r)][1].copy())[None] for r in selected])
                logits=model(x,c,grids,valid)
                if logits.shape!=(len(x),1,256,256) or not torch.isfinite(logits).all(): raise ValueError('context_model_output_contract')
                values.extend(logits.sigmoid().cpu().numpy()[:,0])
        probability=common.restore_probability_mean(body,records,values)
        return (probability>=common.PROTOCOL['threshold'])&body


class ContextTiles(Dataset):
    def __init__(self,root,manifest,ids,prepared):
        self.root=root;self.manifest=manifest;self.prepared=prepared
        self.sources={s['source_id']:s for s in manifest['sources']}
        self.records=[r for r in manifest['crops'] if r['source_id'] in ids]
        self.weights=common.source_weights(self.records)
    def __len__(self): return len(self.records)
    def __getitem__(self,index):
        record=self.records[index];sid=record['source_id']
        data=load_crop(self.root,record,self.sources[sid],self.manifest['purpose'])
        rgb=torch.from_numpy(data['rgb'].copy()).permute(2,0,1).float()/255
        coarse=torch.from_numpy(data['coarse'].copy()).float()[None];label=torch.from_numpy(data['label'].copy()).float()[None]
        grid,valid=self.prepared.grids[grid_key(record)]
        rgb,coarse,label,grid,valid=augment(rgb,coarse,label,torch.from_numpy(grid.copy()),torch.from_numpy(valid.copy())[None])
        rgb=(rgb-torch.tensor([.485,.456,.406])[:,None,None])/torch.tensor([.229,.224,.225])[:,None,None]
        context=torch.from_numpy(self.prepared.context[sid].copy())
        return torch.cat([rgb,coarse]),context,grid,valid,label,torch.tensor(self.weights[index],dtype=torch.float32)


def make_loader(root,manifest,ids,seed,prepared):
    return DataLoader(ContextTiles(root,manifest,ids,prepared),batch_size=4,shuffle=True,
        generator=torch.Generator().manual_seed(seed),num_workers=0)
