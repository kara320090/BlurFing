"""Real stdio/process lifecycle tests with explicitly synthetic photo results."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from experimental_photo_main import PhotoRuntimeConfig,PhotoResidentRuntime,create_app
from experimental_photo_transport_v2 import UploadedPhoto
from test_experimental_photo_v2 import png


@pytest.fixture
def configured(tmp_path):
    bridge=tmp_path/'export_photo_permissions_v1.py';bridge.write_text('# synthetic bridge')
    registry=tmp_path/'registry.json';registry.write_text('[]')
    model=tmp_path/'model';model.mkdir()
    (model/'final_config.private.json').write_text('{}');(model/'final_context_whole_pad.pt').write_bytes(b'fixture')
    jobs=tmp_path/'jobs';jobs.mkdir()
    script='''import argparse,json,os,pathlib,sys,time
sys.path.insert(0,BACKEND)
from test_experimental_photo_v2 import synthetic_payload
p=argparse.ArgumentParser();p.add_argument('--model');p.add_argument('--registry');p.add_argument('--development-replay',action='store_true');p.parse_args()
root=pathlib.Path(__file__).parent
def mode():return (root/'mode').read_text() if (root/'mode').exists() else ''
print(json.dumps(dict(status='wrong' if mode()=='badready' else 'ready',protocol='photo-resident-v29')),flush=True)
for line in sys.stdin:
    job=json.loads(line)
    with (root/'calls.jsonl').open('a') as stream:stream.write(json.dumps(dict(pid=os.getpid(),id=job['id'],request_id=job['request_id']))+'\\n')
    action=mode()
    if action=='delay':time.sleep(30)
    if action=='crash':raise SystemExit(7)
    source=pathlib.Path(job['input']);output=pathlib.Path(job['output']);output.mkdir()
    payload=synthetic_payload(source.read_bytes(),job['request_id'],'synthetic_v23')
    (output/'result.transport.json').write_text(json.dumps(payload))
    print(json.dumps(dict(status='ok',id='foreign' if action=='wrongid' else job['id'])),flush=True)
'''.replace('BACKEND',repr(str(Path(__file__).resolve().parent)))
    bridge.with_name('photo_resident_worker_v29.py').write_text(script,encoding='utf-8')
    return PhotoRuntimeConfig(Path(sys.executable),bridge,registry,model,('synthetic_v23',),10.,False,jobs,True)


def send(client,request_id,value=120):
    return client.post('/v2/photo/protect',files={'image':('input.png',png(np.full((12,16,3),value,np.uint8)),'image/png')},
        data=dict(request_id=request_id,method='photo_synthetic_v23_automatic_experimental',scope='automatic_photo',strength='0.5'))


def ready(client):
    stop=time.monotonic()+10
    while time.monotonic()<stop:
        if client.get('/ready').status_code==200:return
        time.sleep(.05)
    raise AssertionError('synthetic worker did not recover')


def test_reuses_process_but_never_reuses_image_or_request_result(configured):
    app=create_app(configured)
    with TestClient(app) as client:
        ready(client);first=send(client,'one',100);second=send(client,'two',140)
        assert first.status_code==second.status_code==200
        assert first.json()['source_RGB_sha256']!=second.json()['source_RGB_sha256']
        calls=[json.loads(line) for line in (configured.bridge.parent/'calls.jsonl').read_text().splitlines()]
        assert len(calls)==2 and calls[0]['pid']==calls[1]['pid']
        assert calls[0]['id']!=calls[1]['id']
        assert not list(configured.temp_root.iterdir())
    assert app.state.photo_runtime._process is None


@pytest.mark.parametrize('mode,status',[('wrongid',500),('crash',500),('delay',504)])
def test_failed_job_is_reaped_and_new_worker_can_process_next_image(configured,mode,status):
    config=replace(configured,timeout_seconds=.4 if mode=='delay' else 10.)
    marker=config.bridge.parent/'mode'
    with TestClient(create_app(config)) as client:
        ready(client);marker.write_text(mode)
        assert send(client,'bad').status_code==status
        marker.unlink();ready(client)
        assert send(client,'good').status_code==200
        assert not list(config.temp_root.iterdir())


def test_cancel_stops_writer_and_releases_slot(configured):
    async def scenario():
        runtime=PhotoResidentRuntime(configured);marker=configured.bridge.parent/'mode'
        try:
            await runtime.start();marker.write_text('delay')
            upload=UploadedPhoto.decode(png(np.full((12,16,3),120,np.uint8)))
            task=asyncio.create_task(runtime.run(upload,'cancel','synthetic_v23',time.monotonic()+30))
            stop=time.monotonic()+10
            while not (configured.bridge.parent/'calls.jsonl').exists() and time.monotonic()<stop:await asyncio.sleep(.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            marker.unlink();await runtime.start()
            result=await runtime.run(upload,'after','synthetic_v23',time.monotonic()+10)
            assert result['request_id']=='after'
            assert not list(configured.temp_root.iterdir())
        finally:await runtime.close()
    asyncio.run(scenario())


def test_bad_startup_does_not_report_ready(configured):
    (configured.bridge.parent/'mode').write_text('badready')
    with TestClient(create_app(configured)) as client:assert client.get('/ready').status_code==503


def test_wait_completion_cannot_hide_an_outer_cancellation(configured,monkeypatch):
    async def scenario():
        runtime=PhotoResidentRuntime(configured)
        try:
            await runtime.start();old_pid=runtime._process.pid
            original=asyncio.wait_for;injected=False
            async def completion_race(awaitable,timeout):
                nonlocal injected
                result=await original(awaitable,timeout)
                if not injected and getattr(getattr(awaitable,'cr_code',None),'co_name','')=='drain':
                    injected=True;asyncio.current_task().cancel()
                    try:await asyncio.sleep(0)
                    except asyncio.CancelledError:pass
                return result
            monkeypatch.setattr(asyncio,'wait_for',completion_race)
            upload=UploadedPhoto.decode(png(np.full((12,16,3),120,np.uint8)))
            task=asyncio.create_task(runtime.run(upload,'race','synthetic_v23',time.monotonic()+10))
            with pytest.raises(asyncio.CancelledError):await task
            assert injected
            monkeypatch.setattr(asyncio,'wait_for',original)
            await runtime.start();assert runtime._process.pid!=old_pid
            assert not list(configured.temp_root.iterdir())
        finally:await runtime.close()
    asyncio.run(scenario())


def test_resident_configuration_is_explicit_and_engine_limited(configured):
    with pytest.raises(ValueError):replace(configured,resident=1)
    with pytest.raises(ValueError):replace(configured,engines=('native_v12',))
