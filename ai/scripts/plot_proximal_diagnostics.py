"""Render PRIVATE axial signal diagnostics; no GT read and no boundary tuning."""
import argparse,csv,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def render(details,output):
    data=json.loads(details.read_text());output.mkdir(parents=True,exist_ok=False)
    for i,region in enumerate(data['regions']):
        evidence=region.get('proximal_boundary')
        if not evidence:continue
        signals=evidence['signals'];names=list(signals)
        with (output/f'finger_{i}_signals.csv').open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['axial_analysis_row','axial_native_distance_from_tip']+names)
            for row in range(len(signals['width'])):writer.writerow([row,(row-evidence['tip_axial_row'])*evidence['analysis_to_native_scale']]+[signals[k][row] for k in names])
        im=Image.new('RGB',(1100,110*len(names)), 'white');draw=ImageDraw.Draw(im)
        for n,name in enumerate(names):
            values=np.asarray(signals[name],float);low=float(values.min());high=float(values.max());span=max(1e-9,high-low)
            draw.text((10,n*110+5),f'{name} [{low:.3g}, {high:.3g}]',fill='black')
            points=[(int(50+j*1000/max(1,len(values)-1)),int(n*110+95-(v-low)*65/span)) for j,v in enumerate(values)]
            draw.line(points,fill='black',width=2)
            for row in evidence['diagnostic_peak_rows'].get(name,[]):
                x=int(50+row*1000/max(1,len(values)-1));draw.line([(x,n*110+25),(x,n*110+100)],fill='blue')
            fallback=evidence['tip_axial_row']+evidence['geometry_fallback_native']/evidence['analysis_to_native_scale']
            x=int(50+fallback*1000/max(1,len(values)-1));draw.line([(x,n*110+25),(x,n*110+100)],fill='orange',width=2)
        im.save(output/f'finger_{i}_signals_private.png')
    (output/'signal_metadata.private.json').write_text(json.dumps({'source_sha256':data['source_sha256'],'regions':[{'finger_id':r['finger_id'],'axis_xy':r['axis_xy'],'proximal_boundary':r.get('proximal_boundary')} for r in data['regions']]},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--details',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();render(a.details,a.output)
