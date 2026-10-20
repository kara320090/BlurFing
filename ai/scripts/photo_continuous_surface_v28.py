"""Independent continuous ridges with camera sampling and restrained diffuse tone.

Only pad geometry, independent seed and coarse skin/style summaries enter the
material. No donor fingerprint or source ridge raster is used. Appearance is
experimental and must be reviewed at native size as well as magnified.
"""
import secrets
import cv2
import numpy as np
from scipy import ndimage
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile
from photo_synthetic_replacement_v6 import smoothstep
from photo_synthetic_replacement_v10 import sample_style
from photo_synthetic_replacement_v19 import render as legacy

VERSION='continuous_diffuse_fingertip_surface_v28_experimental'


def material(local,u,v,width,length,seed,stats,base,curves):
    # Use a full canonical design even for a small camera fingertip; the old
    # minimum four-native-pixel period made these fingertips look coarse.
    design_scale=400/max(width,length)
    rng=np.random.default_rng(seed ^ 0x2828)
    canonical_pitch=float(np.clip(width*design_scale/rng.uniform(30.,38.),4.,14.))
    yy,xx=np.mgrid[:512,:512]
    support=(abs(xx-255.5)<=max(4.,width*design_scale*.5)) & (abs(yy-255.5)<=max(4.,length*design_scale*.5))
    field,recipe=independent_photographic_field(support,canonical_pitch,seed)
    profile,profile_meta=render_photographic_profile(field,support,canonical_pitch,seed)
    # Supersample small surfaces, cap large ones, then filter the GENERATED
    # response before camera sampling. Do not smooth or blend source pixels.
    scale=min(3.,1024/max(width,length))
    w,h=max(16,round(width*scale)),max(16,round(length*scale))
    gy,gx=np.mgrid[:h,:w].astype(np.float32)
    gu,gv=2*gx/(w-1)-1,2*gy/(h-1)-1
    pu=np.arcsin(np.clip(gu*.72,-.72,.72))/np.arcsin(.72)
    pv=gv*(1+.04*gu*gu)
    coords=np.array([255.5+pv*length*.5*design_scale,255.5+pu*width*.5*design_scale])
    ridge=ndimage.map_coordinates(profile,coords,order=3,mode='nearest',prefilter=True)
    pitch=canonical_pitch/design_scale
    gray=base@np.array([.299,.587,.114]);step=max(1,len(u)//4096)
    design=np.column_stack((np.ones(len(u[::step])),u[::step],v[::step]))
    light=np.linalg.lstsq(design,gray[::step],rcond=None)[0][1:]
    light/=max(1.,float(np.linalg.norm(light)))
    dy,dx=np.gradient(ridge)
    # No sparse pores, ridge cuts, random cross-folds or specular exponent.
    response=.72*ridge+.10*(dx*light[0]+dy*light[1])*pitch*scale/(2*np.pi)
    response=cv2.GaussianBlur(response,(0,0),max(.45,.48*scale))
    sample=np.vstack(((v+1)*(h-1)/2,(u+1)*(w-1)/2))
    relief=ndimage.map_coordinates(response,sample,order=1,mode='nearest',prefilter=False)
    energy=sample_style(stats,u,v)
    amplitude=np.clip(np.hypot(energy[:,1],energy[:,2]),3.,5.)
    detail=np.clip(relief*amplitude,-5.,3.5)
    # Observed broad creases already belong to the coarse base. Let their
    # valleys interrupt detail gently without inventing extra shallow folds.
    fold=np.zeros(len(u))
    for curve in curves:
        q=curve['quadratic_v_from_u'];sigma=max(1.,float(curve['sigma_source_pixels']))
        offset=(v-q[0]-q[1]*u-q[2]*u*u)*length*.5
        fold=np.maximum(fold,np.exp(-.5*(offset/(1.5*sigma))**2))
    distance=ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local]
    fade=smoothstep((distance-1)/max(3.,.025*width))
    detail*=fade*(1-.65*fold)
    values=base+detail[:,None]*np.clip(base/180.,.5,1.3)
    return values,dict(method='continuous_independent_diffuse_ridges_camera_sampled',
        latent_shape=[h,w],maximum_latent_dimension=1024,synthetic_pitch_pixels=pitch,
        field_recipe=recipe,profile_recipe=profile_meta,canonical_design_scale=design_scale,
        camera_filter_sigma_source_pixels=.48,generated_pores=False,
        generated_ridge_interruptions=False,generated_secondary_folds=0,specular_reflection=False,
        bounded_pre_junction_detail_RGB=[-6.5,4.55],
        fingerprint_texture_resolved=bool(width>=4 and len(u)>=32),
        source_pixels_input=False,source_ridge_phase_transferred=False,
        original_pixel_alpha=0.,natural_appearance_validated=False)


def render(rgb,mask,labels,*,seed=None,detail_regions=()):
    if (not isinstance(detail_regions,(tuple,list)) or
            any(type(i) is not int or not 1<=i<=65535 for i in detail_regions) or
            len(set(detail_regions))!=len(detail_regions)):
        raise ValueError('continuous_surface_region_contract')
    if not isinstance(labels,np.ndarray) or labels.dtype!=np.uint16:
        raise ValueError('continuous_surface_labels_contract')
    present={int(i) for i in np.unique(labels) if i};selected=present & set(detail_regions)
    if not selected:return legacy(rgb,mask,labels,seed=seed)
    if seed is None:seed=secrets.randbits(128)
    if type(seed) is not int or not 0<=seed<2**128:raise ValueError('synthetic_seed_unsigned_128bit_required')
    children={int(np.random.SeedSequence([seed,i]).generate_state(1,dtype=np.uint64)[0]):i for i in present}
    if len(children)!=len(present):raise ValueError('continuous_surface_seed_collision')
    def replacement(local,u,v,width,length,child,stats,base,curves):
        if children[child] in selected:return material(local,u,v,width,length,child,stats,base,curves)
        return None
    returned,report=legacy(rgb,mask,labels,seed=seed,generated_material=replacement)
    report['continuous_surface_policy']=dict(version=VERSION,region_ids=sorted(selected),
        original_fingerprint_reconstruction=False,source_ridge_pixels_used=False,
        natural_appearance_validated=False)
    return returned,report
