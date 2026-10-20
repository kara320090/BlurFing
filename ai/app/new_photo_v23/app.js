'use strict';
const $ = id => document.getElementById(id);
let state = null, selected = null, tool = null, points = [], scale = 1;
let busyUI = false, space = false, pan = null, overlayImage = null, drawEpoch = 0, pollTimer = null;
const errorText = {
  stale_photo_or_revision_reload: '사진 또는 편집 상태가 바뀌었습니다. 화면을 다시 확인하세요.',
  polygon_overlaps_another_region: '다른 손끝 영역과 겹칩니다. 점을 수정하거나 기존 영역을 선택해 늘리세요.',
  automatic_detection_failed_manual_edit_available: '자동 검출에 실패했습니다. 새 영역 그리기로 계속할 수 있습니다. 상세 기록은 저장 폴더의 worker.log에 있습니다.',
  no_explicit_visible_region_selected: '지문선이 보이는 영역을 먼저 선택하세요.',
  invalid_source_exif_orientation: '사진의 EXIF 방향 값이 잘못되어 읽지 못했습니다. 원본은 보존되었습니다.',
  unsupported_source_mode: '이 사진의 색상 형식은 지원되지 않습니다. RGB·RGBA·8비트 회색조 JPG/PNG를 선택하세요.',
  job_running_please_wait: '현재 작업이 끝난 후 다시 시도하세요.',
};
function message(text, bad=false) { $('status').textContent=text; $('status').className=bad?'error':''; }
async function api(route, data) {
  const response=await fetch('api/'+route, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const value=await response.json();
  if(!response.ok) throw Error(errorText[value.error]||value.error||'요청 실패');
  return value;
}
function binding(extra={}) {return {id:state.photo.id,revision:state.photo.revision,...extra};}
function imageUrl(part) {return `photo/${state.photo.id}/${part}?revision=${state.photo.revision}`;}
function locked() {return busyUI||!!state?.busy;}
function buttons() {
  const p=state?.photo, lock=locked(), drawing=!!tool;
  $('file').disabled=lock; $('detect').disabled=lock||!p||!state.detector_available||drawing;
  $('new').disabled=lock||!p||drawing;
  for(const id of ['add','erase','delete']) $(id).disabled=lock||!selected||drawing;
  $('close').disabled=lock||points.length<3;
  $('cancel').disabled=lock||!drawing;
  $('undo').disabled=lock||!p?.can_undo||drawing;
  $('confirmed').disabled=lock||!p||drawing;
  $('apply').disabled=lock||drawing||!$('confirmed').checked||!p?.regions.some(r=>r.decision==='visible');
  $('stop').disabled=lock;
  $('view').disabled=lock||drawing;
  for(const element of document.querySelectorAll('.region select')) element.disabled=lock||drawing;
}
function clearDrawing() {tool=null;points=[];for(const id of ['new','add','erase']) $(id).classList.remove('active');}
async function refresh(next) {
  const old=state?.photo, p=next.photo, changed=old?.id!==p?.id||old?.revision!==p?.revision;
  state=next;
  if(changed) {$('confirmed').checked=false;clearDrawing();}
  if(!p) {buttons();return;}
  const newPhoto=old?.id!==p.id;
  if(!p.regions.some(r=>r.region_id===selected)) selected=p.regions[0]?.region_id||null;
  $('filename').textContent=`${p.name} · ${p.width} × ${p.height}`+(p.primary_frame_only?' · 복합 JPEG의 기본 사진 사용':'');
  $('empty').hidden=true; $('stage').style.display='block';
  $('canvas').width=p.width; $('canvas').height=p.height;
  const list=$('regions'); list.replaceChildren();
  if(!p.regions.length) {const note=document.createElement('p');note.className='hint';note.textContent='영역이 없습니다. 자동 검출하거나 새 영역을 그리세요.';list.append(note);}
  for(const r of p.regions) {
    const div=document.createElement('div');div.className='region'+(r.region_id===selected?' selected':'');
    const name=document.createElement('span');name.textContent=`영역 ${r.region_id} · ${r.pixels.toLocaleString()} px`;
    const select=document.createElement('select');select.setAttribute('aria-label',`영역 ${r.region_id} 지문선`);
    for(const [v,t] of [['uncertain','불확실 · 원본 유지'],['visible','보임 · 적용 대상'],['not_observed','관찰되지 않음 · 원본 유지']]) {
      const option=new Option(t,v,v===r.decision,v===r.decision);select.add(option);
    }
    select.onchange=()=>edit({action:'decision',region_id:r.region_id,decision:select.value});
    div.onclick=e=>{if(e.target!==select&&!locked()&&!tool){selected=r.region_id;refresh(state);}};
    div.append(name,select);list.append(div);
  }
  $('result').hidden=!p.result;
  $('view').options[1].disabled=!p.result;
  if(!p.result) $('view').value='original';
  if(p.result) {
    $('counts').textContent=`선택 ${p.result.selected_regions} / 실제 적용 ${p.result.applied_regions} / 확인 필요 ${p.result.review_required}`;
    $('download').href=imageUrl('result/returned.png');
    $('maskDownload').href=imageUrl('result/applied_mask.png');
    $('folder').value=p.result.path;
  }
  $('photo').src=imageUrl($('view').value==='returned'?'result/display.png':'original.png');
  if(newPhoto) fit(); else setScale(scale);
  if(changed||!overlayImage) {
    const epoch=++drawEpoch;
    overlayImage=null;
    const image=new Image();
    image.onload=()=>{if(epoch===drawEpoch){overlayImage=image;draw();}};
    image.src=imageUrl('overlay.png');
  }
  draw(); buttons();
  if(state.busy) {
    message(state.busy==='detect'?'손끝 후보를 찾고 있습니다. 사진에 따라 수 분 걸릴 수 있습니다.':'V23 적용 후 실제 저장 PNG를 검증하고 있습니다.');
    clearTimeout(pollTimer);pollTimer=setTimeout(poll,1000);
  } else if(state.error) message(errorText[state.error]||state.error,true);
}
async function poll() {
  try {
    const was=state?.busy; await refresh(await api('state'));
    if(was&&!state.busy&&!state.error) {
      if(was==='apply') {
        $('view').value='returned';$('overlay').checked=false;await refresh(state);
        message(`완료: ${state.photo.result.applied_regions}개 영역 적용. 결과를 확대해 남은 지문과 경계를 확인하세요.`);
      } else if(!state.photo.regions.length) {
        message('손끝 후보를 찾지 못했습니다. 자동 검출은 완료됐지만 보호 범위가 없습니다. 새 영역을 그리거나 다른 사진을 선택하세요.',true);
      } else {
        const restored=state.photo.candidate_selection?.restored_candidate_components||0;
        message(restored
          ? `후보 ${state.photo.regions.length}개를 불러왔습니다. 경계를 확정하지 못한 ${restored}개 후보는 보정 전 영역으로 표시했습니다. 손끝 경계를 직접 확인·수정하세요.`
          : '자동 후보를 불러왔습니다. 경계를 수정하고 각 영역의 지문선 판정을 선택하세요.');
      }
    }
  } catch(e) {message(e.message,true);}
}
async function perform(action) {
  if(locked()) return;
  busyUI=true;buttons();
  try {await action();} catch(e) {message(e.message,true);}
  finally {busyUI=false;buttons();}
}
async function edit(payload) {
  await perform(async()=>{const next=await api('edit',binding(payload));await refresh(next);message('편집 저장됨. 적용 전 확인 체크를 다시 선택하세요.');});
}
$('file').onchange=()=>perform(async()=>{
  const file=$('file').files[0];if(!file)return;
  if(file.size>40*1024*1024)throw Error('40 MiB 이하의 사진을 선택하세요.');
  message('사진을 읽고 방향과 색상 정보를 확인하고 있습니다.');
  const response=await fetch('api/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});
  const next=await response.json();if(!response.ok)throw Error(errorText[next.error]||next.error);
  overlayImage=null;await refresh(next);message('사진을 불러왔습니다. 자동 검출 또는 새 영역 그리기를 선택하세요.');
  $('file').value='';
});
$('detect').onclick=()=>perform(async()=>{
  if(state.photo.regions.length&&!window.confirm('현재 후보를 자동 검출 결과로 바꿀까요? 이전 편집으로 되돌릴 수 있습니다.'))return;
  await refresh(await api('detect',binding({replace_draft:true})));
});
$('apply').onclick=()=>perform(async()=>{await refresh(await api('apply',binding({confirmed:$('confirmed').checked})));});
for(const id of ['new','add','erase']) $(id).onclick=()=>{
  tool=id;points=[];$('view').value='original';$('overlay').checked=true;$('photo').src=imageUrl('original.png');
  $(id).classList.add('active');$('confirmed').checked=false;buttons();draw();
  message('경계점을 차례로 클릭하세요. Enter로 완료, Esc로 취소합니다.');
};
$('delete').onclick=()=>edit({action:'delete',region_id:selected});
$('undo').onclick=()=>edit({action:'undo'});
$('close').onclick=async()=>{if(points.length>=3)await edit({action:tool,region_id:selected,points});};
$('cancel').onclick=()=>{clearDrawing();buttons();draw();};
$('confirmed').onchange=buttons;
$('view').onchange=()=>refresh(state);
$('overlay').onchange=draw;
function setScale(s) {
  if(!state?.photo)return;scale=Math.min(8,Math.max(.03,s));
  $('stage').style.width=state.photo.width*scale+'px';$('stage').style.height=state.photo.height*scale+'px';
  $('zoom').textContent=Math.round(scale*100)+'%';draw();
}
function fit(){if(state?.photo)setScale(Math.min(($('viewport').clientWidth-16)/state.photo.width,($('viewport').clientHeight-16)/state.photo.height));}
$('fit').onclick=fit;$('one').onclick=()=>setScale(1);
$('regionFit').onclick=()=>{
  const r=state?.photo?.regions.find(r=>r.region_id===selected);if(!r)return;
  const [x,y,x1,y1]=r.bbox,area=$('viewport');
  setScale(Math.min(area.clientWidth/(x1-x+40),area.clientHeight/(y1-y+40)));
  area.scrollLeft=(x+x1)*scale/2-area.clientWidth/2;area.scrollTop=(y+y1)*scale/2-area.clientHeight/2;
};
$('plus').onclick=()=>setScale(scale*1.25);$('minus').onclick=()=>setScale(scale/1.25);
function draw(){
  const canvas=$('canvas'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  if($('view').value!=='original')return;
  if($('overlay').checked&&overlayImage)ctx.drawImage(overlayImage,0,0);
  ctx.lineWidth=2/scale;ctx.font=`${14/scale}px sans-serif`;
  if($('overlay').checked)for(const r of state?.photo?.regions||[]){
    const [x,y,x1,y1]=r.bbox;ctx.strokeStyle=r.region_id===selected?'#fff1a2':'#78e9ce';
    ctx.fillStyle=ctx.strokeStyle;ctx.strokeRect(x,y,x1-x,y1-y);ctx.fillText(String(r.region_id),x+3/scale,y+17/scale);
  }
  if(points.length){
    ctx.strokeStyle='#ffd470';ctx.fillStyle='#ffd470';ctx.beginPath();
    points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke();
    for(const [x,y] of points){ctx.beginPath();ctx.arc(x,y,3/scale,0,Math.PI*2);ctx.fill();}
  }
}
$('canvas').onpointerdown=e=>{
  if(locked()||!state?.photo)return;
  if(!tool||space){pan={x:e.clientX,y:e.clientY,left:$('viewport').scrollLeft,top:$('viewport').scrollTop};$('canvas').setPointerCapture(e.pointerId);return;}
  const box=$('canvas').getBoundingClientRect(),x=Math.floor((e.clientX-box.left)/scale),y=Math.floor((e.clientY-box.top)/scale);
  if(x>=0&&y>=0&&x<state.photo.width&&y<state.photo.height){points.push([x,y]);draw();buttons();}
};
$('canvas').onpointermove=e=>{if(pan){$('viewport').scrollLeft=pan.left+pan.x-e.clientX;$('viewport').scrollTop=pan.top+pan.y-e.clientY;}};
$('canvas').onpointerup=$('canvas').onpointercancel=()=>{pan=null;};
$('viewport').addEventListener('wheel',e=>{
  if(!state?.photo)return;e.preventDefault();const area=$('viewport'),box=area.getBoundingClientRect();
  const x=e.clientX-box.left,y=e.clientY-box.top,px=(area.scrollLeft+x)/scale,py=(area.scrollTop+y)/scale;
  setScale(scale*(e.deltaY<0?1.15:1/1.15));area.scrollLeft=px*scale-x;area.scrollTop=py*scale-y;
},{passive:false});
window.addEventListener('keydown',e=>{
  if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;
  if(e.code==='Space'){space=true;e.preventDefault();}
  if(e.key==='Escape'&&!locked())$('cancel').click();
  if(e.key==='Enter'&&tool&&!$('close').disabled){e.preventDefault();$('close').click();}
  if(e.key==='Backspace'&&tool&&!locked()){e.preventDefault();points.pop();draw();buttons();}
});
window.addEventListener('keyup',e=>{if(e.code==='Space')space=false;});
window.addEventListener('blur',()=>{space=false;pan=null;});
$('stop').onclick=()=>perform(async()=>{await api('stop',{});message('종료했습니다. 저장된 원본·편집·결과는 유지됩니다. 이 탭을 닫아도 됩니다.');});
poll();
