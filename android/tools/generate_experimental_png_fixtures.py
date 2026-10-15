"""Synthetic-only independent PNG fixtures; Pillow verifies every generated pixel."""
import base64, hashlib, io, json, struct, zlib
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'app/src/test/resources/experimental-png'
OUT.mkdir(parents=True,exist_ok=True)
W,H=9,7
sig=b'\x89PNG\r\n\x1a\n'
def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
def sha(x):return hashlib.sha256(x).hexdigest()
rgb=bytes(c for y in range(H) for x in range(W) for c in ((x*29+y*7)%256,(x*11+y*31)%256,(x*43+y*17)%256))
mask=bytes(255 if (x+y)%3==0 else 0 for y in range(H) for x in range(W))
exif=Image.Exif();exif[274]=1
tiff=exif.tobytes()[6:]
def paeth(a,b,c):
    p=a+b-c;ds=[abs(p-a),abs(p-b),abs(p-c)]
    return (a,b,c)[ds.index(min(ds))]
def png(raw,typ,filter_number=0,*,exifbytes=tiff,extra=b'',bit=8,interlace=0,width=W,height=H,zextra=b''):
    bpp=3 if typ==2 else 1
    rows=[];prior=bytes(W*bpp)
    for y in range(H):
        row=raw[y*W*bpp:(y+1)*W*bpp];filtered=[]
        for i,v in enumerate(row):
            a=row[i-bpp] if i>=bpp else 0;b=prior[i];c=prior[i-bpp] if i>=bpp else 0
            pred=(0,a,b,(a+b)//2,paeth(a,b,c))[filter_number]
            filtered.append((v-pred)%256)
        rows.append(bytes([filter_number])+bytes(filtered));prior=row
    ih=chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,bit,typ,0,0,interlace))
    compressed=zlib.compress(b''.join(rows)+extra)+zextra
    cut=max(1,len(compressed)//3)
    ids=b''.join(chunk(b'IDAT',compressed[i:i+cut]) for i in range(0,len(compressed),cut))
    return sig+ih+(chunk(b'eXIf',exifbytes) if exifbytes else b'')+ids+chunk(b'IEND',b'')

manifest={}
for mode,raw,typ in [('RGB',rgb,2),('L',mask,0)]:
    for f in range(5):
        name=f'{mode}-filter{f}.png';data=png(raw,typ,f)
        with Image.open(io.BytesIO(data)) as image:
            image.load();assert image.mode==mode and image.size==(W,H) and image.tobytes()==raw and image.getexif()[274]==1
        (OUT/name).write_bytes(data)
        manifest[name]={'width':W,'height':H,'color_type':typ,'pixel_sha256':sha(raw),'png_sha256':sha(data)}
    output=io.BytesIO();Image.frombytes(mode,(W,H),raw).save(output,'PNG',exif=exif)
    name=f'{mode}-pillow.png';(OUT/name).write_bytes(output.getvalue());manifest[name]={'width':W,'height':H,'color_type':typ,'pixel_sha256':sha(raw),'png_sha256':sha(output.getvalue())}

good=png(rgb,2)
little_tiff=struct.pack('<2sHIHHHIHHI',b'II',42,8,1,274,3,1,1,0,0)
little=png(rgb,2,exifbytes=little_tiff)
with Image.open(io.BytesIO(little)) as image:
    image.load();assert image.tobytes()==rgb and image.getexif()[274]==1
(OUT/'RGB-little-exif.png').write_bytes(little)
def chunks(data):
    at=8;out=[]
    while at<len(data):
        n=struct.unpack_from('>I',data,at)[0];out.append((data[at+4:at+8],data[at+8:at+8+n]));at+=12+n
    return out
parts=chunks(good)
def rep(parts):return sig+b''.join(chunk(t,d) for t,d in parts)
invalid={
    'truncated':good[:-5], 'trailing':good+b'junk','bad-crc':good[:-1]+bytes([good[-1]^1]),
    'duplicate-ihdr':rep([parts[0]]+parts),'duplicate-exif':rep(parts[:2]+[parts[1]]+parts[2:]),
    'unknown-critical':rep(parts[:2]+[(b'ABCD',b'')]+parts[2:]),
    'invalid-reserved':rep(parts[:2]+[(b'abcd',b'')]+parts[2:]),
    'apng':rep(parts[:2]+[(b'acTL',struct.pack('>II',1,0))]+parts[2:]),
    'transparent':rep(parts[:2]+[(b'tRNS',b'\0'*6)]+parts[2:]),
    'rgba':png(bytes(W*H*3),6),'palette':png(mask,3),'rgb16':png(rgb,2,bit=16),'interlaced':png(rgb,2,interlace=1),
    'extra-inflated':png(rgb,2,extra=b'\0'+rgb[:W*3]),'extra-zlib':png(rgb,2,zextra=zlib.compress(b'junk')),
    'compressed-junk':png(rgb,2,zextra=b'junk'),'huge-dimensions':png(rgb,2,width=2**31-1,height=2**31-1),
    'zero-width':png(rgb,2,width=0),
    'nonconsecutive-idat':rep(parts[:3]+[(b'tEXt',b'a\0b')]+parts[3:])
}
e6=Image.Exif();e6[274]=6
invalid['orientation6']=png(rgb,2,exifbytes=e6.tobytes()[6:])
invalid['duplicate-iend']=good+chunk(b'IEND',b'')
for color in (b'iCCP',b'cICP',b'gAMA',b'cHRM',b'mDCV',b'cLLI',b'sRGB',b'sBIT'):
    # CRC-valid color chunks are outside the canonical wire contract, even for sRGB metadata.
    invalid['color-'+color.decode()]=rep(parts[:2]+[(color,b'\0'*32)]+parts[2:])
invalid['ancillary-text']=rep(parts[:2]+[(b'tEXt',b'note\0synthetic')]+parts[2:])
extra_exif=Image.Exif();extra_exif[274]=1;extra_exif[315]='synthetic'
invalid['exif-extra-tag']=png(rgb,2,exifbytes=extra_exif.tobytes()[6:])
invalid['exif-extra-padding']=png(rgb,2,exifbytes=tiff+b'\0')
invalid['exif-no-orientation']=png(rgb,2,exifbytes=b'MM\0*\0\0\0\x08\0\0\0\0\0\0')
for name,data in invalid.items():(OUT/f'invalid-{name}.png').write_bytes(data)
manifest['invalid_names']=list(invalid)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

accepted=bytes(255 if x<4 and 1<=y<=3 else 0 for y in range(H) for x in range(W))
rejected=bytes(255 if 5<=x<=7 and 3<=y<=5 else 0 for y in range(H) for x in range(W))
returned=bytearray(rgb);returned[(2*W+1)*3]^=128
def pillow(raw,mode):
    out=io.BytesIO();Image.frombytes(mode,(W,H),raw).save(out,'PNG',exif=exif);return out.getvalue()
def wire_mask(raw):
    data=pillow(raw,'L');return dict(encoding='png_uint8_0_255',image_base64=base64.b64encode(data).decode(),png_sha256=sha(data),boolean_pixel_sha256=sha(bytes(v//255 for v in raw)),pixels=sum(v//255 for v in raw))
(OUT/'L-nonbinary.png').write_bytes(pillow(bytes([127])+accepted[1:],'L'))
template=dict(contract_version='photo-experimental-v2',request_id='synthetic',result_kind='experimental',method='photo_native_v12_experimental',photo_engine='native_v12',status='partial_success',image_base64=base64.b64encode(pillow(bytes(returned),'RGB')).decode(),mime_type='image/png',image_width=W,image_height=H,source_exif_orientation=1,coordinate_system='encoded_original_pixels',source_sha256=sha(pillow(rgb,'RGB')),source_RGB_sha256=sha(rgb),returned_RGB_sha256=sha(bytes(returned)),candidate_components=2,transformed_components=1,rejected_components=1,changed_RGB_pixels=1,accepted_permission_mask=wire_mask(accepted),rejected_permission_mask=wire_mask(rejected),region_display_bounds=[dict(region_id=1,status='transformed',reason_code='TRANSFORMED',mask_pixels=12,changed_RGB_pixels=1,permission_boolean_sha256=sha(bytes(v//255 for v in accepted)),x=0,y=1/H,width=4/W,height=3/H,bounds_are_not_filled_permission=True),dict(region_id=2,status='rejected',reason_code='REJECT_PITCH_UNOBSERVED',mask_pixels=9,changed_RGB_pixels=0,permission_boolean_sha256=sha(bytes(v//255 for v in rejected)),x=5/W,y=3/H,width=3/W,height=3/H,bounds_are_not_filled_permission=True)],bounds_are_not_filled_permission=True,processing_ms=1,warnings=['EXPERIMENTAL_UNAPPROVED','UNDETECTED_FINGERPRINTS_POSSIBLE','COUNTS_ARE_PERMISSION_COMPONENTS_NOT_FINGERS','REJECTED_REGIONS_RETAIN_ORIGINAL_PIXELS'],privacy_validated=False,production_approved=False,complete_photo_protection_verified=False,independent_final_test=False,evaluation=None)
(OUT/'response-pillow.json').write_text(json.dumps(template),encoding='utf-8')
print(json.dumps({'Pillow_verified_valid_fixtures':13,'invalid_fixtures':len(invalid),'real_photos_included':0}))
