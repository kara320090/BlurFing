"""Versioned observed-pitch contract; evidence hashes are integrity, not signatures."""
from dataclasses import dataclass,asdict
import hashlib,json,math,re
import numpy as np

MIN_PATCHES=6
MAX_RELATIVE_DIFFERENCE=.15

@dataclass
class ExternalPitchEvidence:
    pitch_value:float|None
    pitch_unit:str
    coordinate_space:str
    image_scale:float
    orientation_deg:float
    observer_name:str
    observer_version:str
    patch_count:int
    accepted_patch_count:int
    cue_results:dict
    agreement_result:dict
    evidence_hash:str
    source_image_sha256:str
    mask_pixel_sha256:str
    image_shape:list
    evidence_status:str
    observed_image_pixel_sha256:str=""
    schema_version:str="external-pitch-v1"
    def payload(self):return {k:v for k,v in asdict(self).items() if k!='evidence_hash'}
    def seal(self):self.evidence_hash=hashlib.sha256(json.dumps(self.payload(),sort_keys=True,allow_nan=False).encode()).hexdigest();return self
    def validate(self,source_sha,mask_sha,shape,coordinate_space,image_scale,observed_image_pixel_sha256=None):
        if self.schema_version!='external-pitch-v1':raise ValueError('unsupported_evidence_schema')
        if self.source_image_sha256!=source_sha or not re.fullmatch('[0-9a-f]{64}',source_sha):raise ValueError('source_hash_mismatch')
        if self.mask_pixel_sha256!=mask_sha or self.image_shape!=list(shape):raise ValueError('ROI_mask_contract_mismatch')
        if self.coordinate_space!=coordinate_space or self.coordinate_space not in ['native_source_pixels','normalized_working_pixels'] or self.pitch_unit!='pixels':raise ValueError('coordinate_space_mismatch')
        if not math.isfinite(self.image_scale) or self.image_scale<=0 or self.image_scale!=image_scale or (coordinate_space=='native_source_pixels' and image_scale!=1):raise ValueError('scale_mismatch')
        if observed_image_pixel_sha256 is not None and self.observed_image_pixel_sha256!=observed_image_pixel_sha256:raise ValueError('observed_pixels_mismatch')
        expected=hashlib.sha256(json.dumps(self.payload(),sort_keys=True,allow_nan=False).encode()).hexdigest()
        if self.evidence_hash!=expected:raise ValueError('evidence_hash_mismatch')
        if self.evidence_status!='accepted':raise ValueError(self.evidence_status)
        if isinstance(self.patch_count,bool) or isinstance(self.accepted_patch_count,bool) or not isinstance(self.patch_count,int) or not isinstance(self.accepted_patch_count,int) or not MIN_PATCHES<=self.accepted_patch_count<=self.patch_count:raise ValueError('insufficient_patches')
        ac=self.cue_results.get('autocorrelation',{});fft=self.cue_results.get('fft',{})
        for cue in [ac,fft]:
            value=cue.get('pitch')
            if cue.get('valid') is not True or isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 2<=value<=50:raise ValueError('no_periodicity')
        diff=abs(ac['pitch']-fft['pitch'])/((ac['pitch']+fft['pitch'])/2)
        if diff>MAX_RELATIVE_DIFFERENCE or self.agreement_result.get('passed') is not True:raise ValueError('cue_disagreement')
        if self.agreement_result.get('orientation_consistent') is not True or not math.isfinite(self.orientation_deg):raise ValueError('unstable_orientation')
        if self.pitch_value is None or not math.isfinite(self.pitch_value) or not 2<=self.pitch_value<=50:raise ValueError('pitch_out_of_range')
        if abs(self.pitch_value-(ac['pitch']+fft['pitch'])/2)>1e-9:raise ValueError('pitch_cue_value_mismatch')
        patches=self.cue_results.get('patches',[])
        accepted=[p for p in patches if p.get('accepted') is True]
        if len(accepted)!=self.accepted_patch_count:raise ValueError('missing_patch_evidence')
        for p in accepted:
            values=[p.get(k) for k in ['autocorrelation','fft','correlation','spectral_energy_fraction','coherence','orientation_deg']]
            if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('invalid_patch_evidence')
            if not 2<=p['autocorrelation']<=50 or not 2<=p['fft']<=50 or p['correlation']<.6 or p['spectral_energy_fraction']<.5 or p['coherence']<.65 or abs(p['autocorrelation']-p['fft'])/((p['autocorrelation']+p['fft'])/2)>.15:raise ValueError('invalid_patch_evidence')
        if abs(float(np.median([p['autocorrelation'] for p in accepted]))-ac['pitch'])>1e-9 or abs(float(np.median([p['fft'] for p in accepted]))-fft['pitch'])>1e-9:raise ValueError('cue_aggregation_mismatch')
        spread=self.agreement_result.get('relative_IQR')
        if not isinstance(spread,(int,float)) or not math.isfinite(spread) or not 0<=spread<=MAX_RELATIVE_DIFFERENCE:raise ValueError('multi_patch_disagreement')
        values=np.array([(p['autocorrelation']+p['fft'])/2 for p in accepted])
        actual_spread=float((np.percentile(values,75)-np.percentile(values,25))/np.median(values))
        if actual_spread>MAX_RELATIVE_DIFFERENCE or abs(actual_spread-spread)>1e-9:raise ValueError('multi_patch_disagreement')
        native=self.pitch_value/self.image_scale
        if not 2<=native<=50:raise ValueError('native_pitch_out_of_range')
        return dict(measured_pitch=self.pitch_value,measured_space=self.coordinate_space,image_scale=self.image_scale,pitch_native=self.pitch_value/self.image_scale,pitch_renderer=self.pitch_value,conversion='native = measured / working_scale; renderer = measured',silent_clamp=False)
