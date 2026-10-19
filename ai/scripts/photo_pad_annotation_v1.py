"""Loopback-only human annotation of complete visible palmar fingertip pads.

No model predictions are loaded. Drafts are not GT. Only an explicit per-image
human attestation publishes a reviewed mask, in original encoded coordinates.
"""
import argparse
import hashlib
import io
import json
import os
import secrets
import shutil
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np
from PIL import Image,ImageDraw,ImageOps
from pad_refinement_data_contract_v2 import checked_bytes,validate_source_id,native_shape

VERSION='whole_pad_human_annotation_v1'
POLICY='whole_visible_palmar_distal_pad_v1'
LABELS={'valid_positive','non_target','ambiguous_unusable'}
MAX_BODY=2*1024**2
ASSETS=Path(__file__).resolve().parent.parent/'app/pad_annotation'
INVERSE={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,
         5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_90,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_270}


def digest(data):return hashlib.sha256(data).hexdigest()


def write_json(path,data):
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()


def inverse_mask(display,orientation):
    if type(orientation) is not int or orientation not in range(1,9):raise ValueError('invalid_EXIF')
    return display.transpose(INVERSE[orientation]) if orientation in INVERSE else display.copy()


def validate_points(points,width,height,closed):
    if not isinstance(points,list) or len(points)>4096 or (closed and len(points)<3):raise ValueError('invalid_polygon_points')
    for point in points:
        if (not isinstance(point,list) or len(point)!=2 or any(type(p) is not int for p in point) or
                not 0<=point[0]<width or not 0<=point[1]<height):raise ValueError('polygon_outside_native_display')
    if closed:
        area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
        if len({tuple(p) for p in points})<3 or area==0:raise ValueError('polygon_has_no_area')


class Project:
    def __init__(self,roster,state):
        self.roster_path=Path(roster).resolve();raw=self.roster_path.read_bytes()
        if len(raw)>4*1024**2:raise ValueError('roster_too_large')
        roster=json.loads(raw.decode('utf-8-sig'))
        if roster.get('version')!='whole_pad_annotation_roster_v1' or roster.get('data_role') not in ['diagnostic_development','synthetic_fixture']:
            raise ValueError('annotation_roster_contract')
        if not isinstance(roster.get('sources'),list) or not 1<=len(roster['sources'])<=128:raise ValueError('annotation_source_count')
        self.synthetic=roster['data_role']=='synthetic_fixture';self.sources={};hashes=set()
        for row in roster['sources']:
            sid=row['source_id'];validate_source_id(sid)
            if sid in self.sources or row['source_sha256'] in hashes:raise ValueError('duplicate_annotation_source')
            source=Path(row['source_path'])
            if not source.is_absolute():raise ValueError('absolute_source_path_required')
            row=dict(row,source_path=str(source));data=checked_bytes(source,row['source_sha256'])
            with Image.open(io.BytesIO(data)) as image:
                native_shape(dict(height=image.height,width=image.width,coordinate_system='encoded_original_pixels'))
                orientation=image.getexif().get(274,1)
                if image.mode not in ['RGB','L'] or type(orientation) is not int or orientation not in range(1,9):raise ValueError('annotation_source_image_contract')
                if any(type(row.get(k)) is not int for k in ['width','height','exif_orientation']) or (image.width,image.height,orientation)!=(row['width'],row['height'],row['exif_orientation']):raise ValueError('annotation_source_geometry_mismatch')
                size=image.size[::-1] if orientation>=5 else image.size
            row.update(display_width=size[0],display_height=size[1]);self.sources[sid]=row;hashes.add(row['source_sha256'])
        if Path(state).is_symlink():raise ValueError('separate_private_state_required')
        self.state=Path(state).resolve()
        if self.state in [Path(r['source_path']).parent for r in self.sources.values()]:raise ValueError('separate_private_state_required')
        self.state.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.images={}
        header=dict(version=VERSION,policy=POLICY,roster_sha256=digest(raw),data_role=roster['data_role'])
        path=self.state/'project.json'
        if path.exists():
            if json.loads(path.read_text(encoding='utf-8'))!=header:raise ValueError('annotation_project_roster_mismatch')
        else:write_json(path,header)

    def source(self,sid):
        if sid not in self.sources:raise ValueError('unknown_annotation_source')
        row=self.sources[sid];return row,checked_bytes(row['source_path'],row['source_sha256'])

    def image(self,sid):
        with self.lock:
            row,data=self.source(sid)
            if sid not in self.images:
                with Image.open(io.BytesIO(data)) as image:
                    rgb=image.convert('RGB');upright=ImageOps.exif_transpose(image).convert('RGB')
                    for key,value in [('encoded_RGB_sha256',np.asarray(rgb)),('upright_RGB_sha256',np.asarray(upright))]:
                        if row.get(key) and digest(value.tobytes())!=row[key]:raise ValueError('source_decoded_RGB_mismatch')
                    stream=io.BytesIO();upright.save(stream,format='PNG')
                    if len(self.images)>=2:self.images.pop(next(iter(self.images)))
                    self.images[sid]=stream.getvalue()
            return self.images[sid]

    def folder(self,sid):
        if sid not in self.sources:raise ValueError('unknown_annotation_source')
        folder=self.state/'annotations'/sid
        for part in [self.state/'annotations',folder]:
            if part.is_symlink():raise ValueError('annotation_state_symlink_forbidden')
        return folder

    def current(self,sid):
        self.source(sid);folder=self.folder(sid);pointer=folder/'latest.json'
        if not pointer.exists():return dict(revision=0,ops=[],pending_points=[],pending_mode='add',label='valid_positive',status='draft',notes='',acquisition_group='',human_annotation=False)
        latest=json.loads(pointer.read_text(encoding='utf-8'));revision=latest['revision']
        if type(revision) is not int or revision<1:raise ValueError('annotation_revision_corrupt')
        path=folder/f'rev-{revision:06d}'/'annotation.json'
        value=json.loads(checked_bytes(path,latest['annotation_sha256']).decode('utf-8'))
        if value['source_sha256']!=self.sources[sid]['source_sha256'] or value['revision']!=revision:raise ValueError('annotation_revision_binding_mismatch')
        assets=value.get('review_assets',{})
        required={'source.json','ground_truth_mask.png','preview.png'} if value['status']!='draft' else set()
        if not isinstance(assets,dict) or set(assets)!=required:raise ValueError('annotation_review_assets_contract')
        for name,sha in assets.items():checked_bytes(path.parent/name,sha)
        return value

    def overview(self):
        with self.lock:
            rows=[]
            for sid,row in self.sources.items():
                current=self.current(sid)
                rows.append(dict(id=sid,filename=Path(row['source_path']).name,width=row['display_width'],height=row['display_height'],
                    status=current['status'],revision=current['revision'],human_annotation=current['human_annotation']))
            return dict(version=VERSION,policy=POLICY,sources=rows,synthetic_fixture=self.synthetic,
                reviewed=sum(r['status']!='draft' for r in rows),total=len(rows),training_performed=False)

    def save(self,sid,payload):
        with self.lock:
            row,_=self.source(sid);current=self.current(sid)
            revision=payload.get('expected_revision')
            if type(revision) is not int or revision!=current['revision']:raise ValueError('annotation_revision_conflict')
            reviewed=payload.get('reviewed');attestation=payload.get('attestation')
            if type(reviewed) is not bool or type(attestation) is not bool or (reviewed and not attestation):raise ValueError('explicit_human_review_required')
            label=payload.get('label');ops=payload.get('ops');pending=payload.get('pending_points',[]);pending_mode=payload.get('pending_mode','add')
            if not isinstance(label,str) or label not in LABELS or not isinstance(ops,list) or len(ops)>256:raise ValueError('annotation_payload_contract')
            if pending_mode not in ['add','erase']:raise ValueError('annotation_polygon_mode')
            width,height=row['display_width'],row['display_height'];validate_points(pending,width,height,False)
            if reviewed and pending:raise ValueError('finish_or_cancel_open_polygon')
            count=len(pending);display=Image.new('L',(width,height));draw=ImageDraw.Draw(display)
            for op in ops:
                if not isinstance(op,dict) or set(op)!={'mode','points'} or op['mode'] not in ['add','erase']:raise ValueError('annotation_polygon_mode')
                validate_points(op['points'],width,height,True);count+=len(op['points'])
                if count>20000:raise ValueError('annotation_point_resource_limit')
                draw.polygon([tuple(p) for p in op['points']],fill=255 if op['mode']=='add' else 0)
            mask=inverse_mask(display,row['exif_orientation']);nonempty=mask.getbbox() is not None
            if reviewed and label=='valid_positive' and not nonempty:raise ValueError('positive_annotation_requires_whole_pad_mask')
            if reviewed and label=='non_target' and nonempty:raise ValueError('non_target_requires_empty_mask')
            notes=payload.get('notes','');group=payload.get('acquisition_group','')
            if not isinstance(notes,str) or len(notes)>2000 or not isinstance(group,str) or len(group)>100:raise ValueError('annotation_text_contract')
            if reviewed and label=='ambiguous_unusable' and not notes.strip():raise ValueError('ambiguous_reason_required')
            # A crash after publishing a revision directory but before moving
            # latest.json leaves an orphan. Preserve it and choose a fresh ID.
            folder=self.folder(sid)
            existing=[int(p.name[4:]) for p in folder.glob('rev-*') if p.name[4:].isascii() and p.name[4:].isdigit()]
            human=reviewed and not self.synthetic;revision=max([revision]+existing)+1
            record=dict(version=VERSION,policy=POLICY,source_id=sid,source_sha256=row['source_sha256'],revision=revision,
                ops=ops,pending_points=pending,pending_mode=pending_mode,label=label,status=label if reviewed else 'draft',notes=notes,
                acquisition_group=group.strip(),group_provenance='human_declared_not_independently_verified' if group.strip() else 'unknown',
                acquisition_group_verified=False,person_independence_verified=False,human_annotation=human,
                explicit_review_attestation=bool(reviewed and attestation),saved_at=datetime.now(timezone.utc).isoformat())
            folder.mkdir(parents=True,exist_ok=True)
            temporary=Path(tempfile.mkdtemp(prefix='.pending-',dir=folder));destination=folder/f'rev-{revision:06d}'
            try:
                if reviewed:
                    mask.save(temporary/'ground_truth_mask.png');mask_bytes=(temporary/'ground_truth_mask.png').read_bytes()
                    metadata=dict(schema_version='1.0',source_filename=Path(row['source_path']).name,source_sha256=row['source_sha256'],
                        image_width=row['width'],image_height=row['height'],exif_orientation=row['exif_orientation'],
                        coordinate_system='encoded_original_pixels',polygon_coordinate_system='exif_transposed_display_pixels',
                        annotation_type='human_reviewed_fingerprint_pad' if human else 'synthetic_test_annotation',
                        human_annotation=human,annotation_status=label,mask_sha256=digest(mask_bytes),
                        polygon_count=sum(op['mode']=='add' for op in ops),mask_semantics=POLICY,annotation_tool=VERSION,
                        human_review_attestation=record['explicit_review_attestation'],notes=notes,
                        acquisition_group=record['acquisition_group'] or 'unknown',group_provenance=record['group_provenance'],
                        acquisition_group_verified=False,person_independence_verified=False,
                        data_role='synthetic_fixture' if self.synthetic else 'diagnostic_development',independent_final_test=False,private=True)
                    for key in ['encoded_RGB_sha256','upright_RGB_sha256']:
                        if key in row:metadata[key]=row[key]
                    write_json(temporary/'source.json',metadata)
                    with Image.open(io.BytesIO(self.image(sid))) as im:
                        preview=im.convert('RGB');preview.thumbnail((1000,1000))
                    overlay=display.resize(preview.size,Image.Resampling.NEAREST);tint=Image.new('RGB',preview.size,(30,220,130))
                    preview=Image.composite(Image.blend(preview,tint,.35),preview,overlay);preview.save(temporary/'preview.png')
                    record['review_assets']={name:digest((temporary/name).read_bytes()) for name in ['source.json','ground_truth_mask.png','preview.png']}
                else:record['review_assets']={}
                write_json(temporary/'annotation.json',record)
                self.source(sid)
                os.replace(temporary,destination)
                write_json(folder/'latest.json',dict(revision=revision,annotation_sha256=digest((destination/'annotation.json').read_bytes())))
            finally:
                if temporary.exists():
                    if temporary.is_symlink() or temporary.resolve().parent!=folder.resolve() or not temporary.name.startswith('.pending-'):
                        raise RuntimeError('annotation_cleanup_containment_failed')
                    shutil.rmtree(temporary)
            return record

    def export(self):
        with self.lock:
            selected=[]
            for sid in self.sources:
                current=self.current(sid)
                if current['status']!='draft':selected.append((sid,current))
            if not selected:raise ValueError('no_explicitly_reviewed_annotations')
            name='BlurFing_manual_GT_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]+'.zip'
            folder=self.state/'exports';folder.mkdir(exist_ok=True);path=folder/name;hashes={};roster=[]
            with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                def add(name,data):archive.writestr(name,data);hashes[name]=digest(data)
                for sid,record in selected:
                    row,data=self.source(sid);source_name=Path(row['source_path']).name
                    image_name=f'images/{sid}/{source_name}';add(image_name,data)
                    root=self.folder(sid)/f'rev-{record["revision"]:06d}'
                    for filename in ['source.json','ground_truth_mask.png','preview.png','annotation.json']:
                        content=checked_bytes(root/filename,record['review_assets'][filename]) if filename!='annotation.json' else (root/filename).read_bytes()
                        add(f'ground_truth_training/{sid}/{filename}',content)
                    roster.append(dict(source_id=sid,source=image_name,GT_folder=f'ground_truth_training/{sid}',
                        annotation_status=record['status'],acquisition_group=record['acquisition_group'] or 'unknown',
                        group_provenance=record['group_provenance'],human_annotation=record['human_annotation']))
                add('annotation_roster.private.json',json.dumps(dict(version=VERSION,sources=roster,
                    data_role='synthetic_fixture' if self.synthetic else 'diagnostic_development',
                    training_performed=False,independent_final_test=False),ensure_ascii=False,indent=2).encode())
                archive.writestr('files.sha256.json',json.dumps(hashes,indent=2))
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:raise RuntimeError('annotation_export_CRC_failed')
                if any(digest(archive.read(n))!=s for n,s in hashes.items()):raise RuntimeError('annotation_export_hash_failed')
            checksum=digest(path.read_bytes());path.with_name(name+'.sha256').write_text(checksum+'  '+name+'\n',encoding='ascii')
            return dict(filename=name,sha256=checksum,reviewed=len(selected),unreviewed=len(self.sources)-len(selected))


def make_server(project,port=0,*,assets=None,export_prefix='BlurFing_manual_GT_'):
    assets=ASSETS if assets is None else Path(assets)
    token=secrets.token_urlsafe(24);prefix='/s/'+token+'/'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,data,content_type='application/json; charset=utf-8',download=None):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if download:self.send_header('Content-Disposition','attachment; filename="'+download+'"')
            self.end_headers();self.wfile.write(data)
        def route(self):
            origin='http://127.0.0.1:'+str(self.server.server_address[1])
            if self.headers.get('Host')!=origin.removeprefix('http://'):raise ValueError('invalid_local_host')
            path=urlsplit(self.path).path
            if not path.startswith(prefix):raise ValueError('invalid_session')
            return path[len(prefix):],origin
        def do_GET(self):
            try:
                path,_=self.route()
                if path in ['','index.html','app.js','style.css']:
                    name=path or 'index.html';types={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}
                    return self.send(200,(assets/name).read_bytes(),types[name])
                if path=='api/project':return self.send(200,project.overview())
                if path.startswith('api/state/'):return self.send(200,project.current(path[len('api/state/'):]))
                if path.startswith('image/'):return self.send(200,project.image(path[len('image/'):]),'image/png')
                if path.startswith('download/'):
                    name=path[len('download/'):]
                    if Path(name).name!=name or not name.startswith(export_prefix) or not name.endswith(('.zip','.zip.sha256')):raise ValueError('invalid_export_name')
                    file=project.state/'exports'/name
                    if file.is_symlink() or not file.is_file():raise ValueError('export_not_found')
                    return self.send(200,file.read_bytes(),'application/octet-stream',name)
                raise ValueError('unknown_route')
            except (ValueError,KeyError,OSError) as error:self.send(400,dict(error=str(error) if isinstance(error,ValueError) else 'local_asset_unavailable'))
        def do_POST(self):
            try:
                path,origin=self.route()
                if self.headers.get('Origin')!=origin or self.headers.get_content_type()!='application/json':raise ValueError('local_origin_and_JSON_required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=MAX_BODY:raise ValueError('annotation_request_size')
                payload=json.loads(self.rfile.read(size).decode('utf-8'))
                if not isinstance(payload,dict):raise ValueError('JSON_object_required')
                if path.startswith('api/save/'):return self.send(200,project.save(path[len('api/save/'):],payload))
                if path=='api/export':return self.send(200,project.export())
                if path=='api/stop':
                    self.send(200,dict(stopped=True));threading.Thread(target=self.server.shutdown,daemon=True).start();return
                raise ValueError('unknown_route')
            except (ValueError,KeyError,OSError) as error:self.send(409 if str(error)=='annotation_revision_conflict' else 400,dict(error=str(error) if isinstance(error,ValueError) else 'local_asset_unavailable'))
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    return server,'http://127.0.0.1:'+str(server.server_address[1])+prefix


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--roster',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args();project=Project(args.roster,args.state);server,url=make_server(project,args.port)
    session=dict(url=url,pid=os.getpid(),version=VERSION,roster_sha256=digest(project.roster_path.read_bytes()),script_sha256=digest(Path(__file__).read_bytes()))
    write_json(project.state/'session.private.json',session);print(json.dumps(dict(status='ready',url=url)),flush=True)
    try:server.serve_forever()
    finally:server.server_close()
