"""Thin Tk GUI for the common CLI. No detector/renderer code is duplicated."""
import argparse,json,subprocess,sys,tempfile,threading,shutil,time,os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox
from PIL import Image,ImageTk,ImageOps
ROOT=Path(__file__).resolve().parents[2]
class App:
    def __init__(self,root,*,photo_engine='legacy',photo_model=None,consumed_registry=None,development_replay=False):
        if photo_engine not in ('legacy','native_v12','distal_v13','pose_v14') or type(development_replay) is not bool:raise ValueError('Invalid photo engine/replay configuration')
        self.root=root;root.title('BlurFing — development fail-closed pipeline');self.source=None;self.output=None;self.photo=None
        self._generation=0;self._output_generation=None;self._worker_lock=threading.Lock()
        for name,callback in [('Select image',self.select),('Process',self.process),('Runtime check',self.runtime),('Benchmark (1 + 10)',self.benchmark),('Save output',self.save)]:
            button=tk.Button(root,text=name,command=callback);button.pack(fill='x')
            if name=='Save output':self.save_button=button;button.config(state='disabled')
        settings=tk.LabelFrame(root,text='PHOTO engine — experimental protection remains unapproved');settings.pack(fill='x')
        self.photo_engine=tk.StringVar(root,value=photo_engine);self.photo_model=tk.StringVar(root,value=str(photo_model or ''))
        self.consumed_registry=tk.StringVar(root,value=str(consumed_registry or ''));self.development_replay=tk.BooleanVar(root,value=development_replay)
        tk.OptionMenu(settings,self.photo_engine,'legacy','native_v12','distal_v13','pose_v14').grid(row=0,column=0,sticky='w')
        tk.Label(settings,text='native_v12: V6 model + registry. distal_v13/pose_v14: geometry experiments, boundary review required. pose_v14 requires external hand runtime; one full hand only.',wraplength=760,justify='left').grid(row=0,column=1,columnspan=2,sticky='w')
        tk.Button(settings,text='V6 model folder',command=self.select_model).grid(row=1,column=0,sticky='ew');tk.Entry(settings,textvariable=self.photo_model,width=70).grid(row=1,column=1,columnspan=2,sticky='ew')
        tk.Button(settings,text='Consumed registry',command=self.select_registry).grid(row=2,column=0,sticky='ew');tk.Entry(settings,textvariable=self.consumed_registry,width=70).grid(row=2,column=1,columnspan=2,sticky='ew')
        tk.Checkbutton(settings,text='Development replay: allow previously used photos; never independent evaluation',variable=self.development_replay).grid(row=3,column=0,columnspan=3,sticky='w')
        settings.columnconfigure(1,weight=1)
        self.label=tk.Label(root,text=self.engine_notice(),wraplength=950);self.label.pack();self.preview=tk.Label(root);self.preview.pack();self.text=tk.Text(root,width=90,height=15);self.text.pack()
        for variable in (self.photo_engine,self.photo_model,self.consumed_registry,self.development_replay):variable.trace_add('write',self.configuration_changed)
    def configuration_changed(self,*_):
        self.invalidate_result();self.label.config(text='Configuration changed; process again. '+self.engine_notice())
    def engine_notice(self):
        if self.photo_engine.get()=='distal_v13':return 'Geometry experiment: boundary review required; regression observed on existing annotations. Production/privacy remain unapproved.'
        if self.photo_engine.get()=='pose_v14':return 'Pose geometry experiment: boundary review required; one full hand only. Missing or multiple hand poses are rejected; production/privacy remain unapproved.'
        return 'PHOTO detector and production readiness remain unapproved.'
    def select_model(self):
        folder=filedialog.askdirectory(title='Private completed V6 model folder')
        if folder:self.photo_model.set(folder)
    def select_registry(self):
        path=filedialog.askopenfilename(title='Private consumed-source registry',filetypes=[('JSON','*.json')])
        if path:self.consumed_registry.set(path)
    def photo_arguments(self):
        engine=self.photo_engine.get()
        if engine=='legacy':return []
        if engine not in ('native_v12','distal_v13','pose_v14'):raise ValueError('Unknown PHOTO engine')
        model=self.photo_model.get().strip();registry=self.consumed_registry.get().strip()
        if not registry or (engine=='native_v12' and not model):raise ValueError('Select the private consumed registry and, for native_v12, the completed V6 model folder.')
        arguments=['--photo-engine',engine,'--consumed-registry',registry]
        if engine=='native_v12':arguments+=['--photo-model',model]
        if self.development_replay.get():arguments.append('--development-replay')
        return arguments
    def invalidate_result(self):
        self._generation+=1;self.output=None;self.photo=None;self._output_generation=None
        self.preview.config(image='');self.text.delete('1.0','end');self.save_button.config(state='disabled')
        return self._generation
    def select(self):
        source=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.bmp *.tif *.tiff')])
        if not source:return
        self.invalidate_result();self.source=source;self.label.config(text=Path(source).name)
    def execute(self,script,args):
        interpreter=os.environ.get('BLURFING_CORE_PYTHON') or sys.executable
        if Path(interpreter).name.lower()=='pythonw.exe':interpreter=str(Path(interpreter).with_name('python.exe'))
        if getattr(sys,'frozen',False) and not os.environ.get('BLURFING_CORE_PYTHON'):raise RuntimeError('Set BLURFING_CORE_PYTHON to the configured core Python executable')
        result=subprocess.run([interpreter,str(ROOT/'scripts'/script),*args],shell=False,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);data=json.loads(result.stdout)
        if result.returncode or data.get('status')=='error':raise RuntimeError(data.get('reason') or data.get('error','CLI failure'))
        return data
    def job(self,work,complete):
        generation=self._generation
        def deliver(value):
            if generation==self._generation:complete(value)
        def report_error(message):
            if generation==self._generation:messagebox.showerror('BlurFing',message)
        def run():
            try:
                # Large model subprocesses from this window must not overlap.
                with self._worker_lock:
                    if generation!=self._generation:return
                    value=work()
            except Exception as exc:
                message=str(exc);self.root.after(0,lambda:report_error(message))
            else:self.root.after(0,lambda:deliver(value))
        worker=threading.Thread(target=run,daemon=True);worker.start();return worker
    def process(self):
        if not self.source:return
        try:photo_arguments=self.photo_arguments()
        except ValueError as exc:messagebox.showerror('BlurFing',str(exc));return
        source=self.source;generation=self.invalidate_result();engine=self.photo_engine.get();folder=str(Path(tempfile.mkdtemp(prefix='blurfing_gui_'))/'result');self.label.config(text=f'Processing: {Path(source).name}')
        def complete(data):
            if generation!=self._generation or source!=self.source:return
            output=data['output_path']
            with Image.open(output) as image:
                preview=ImageOps.exif_transpose(image);preview.thumbnail((900,550));photo=ImageTk.PhotoImage(preview)
            notice=' | geometry experiment: review boundaries' if engine in ('distal_v13','pose_v14') else ''
            self.output=output;self.photo=photo;self._output_generation=generation;self.text.delete('1.0','end');self.text.insert('end',json.dumps(data,indent=2));self.preview.config(image=self.photo);self.label.config(text=f"{engine} / {data['input_type']}: {data['status']} | candidate regions {data['fingerprints_detected']}, transformed {data['fingerprints_transformed']}, rejected {data['fingerprints_rejected']}"+notice);self.save_button.config(state='normal')
        self.job(lambda:self.execute('protect_fingerprint.py',['--input',source,'--output',folder,*photo_arguments]),complete)
    def runtime(self):self.job(lambda:self.execute('check_unified_runtime.py',[]),lambda r:(self.text.delete('1.0','end'),self.text.insert('end',json.dumps(r,indent=2))))
    def save(self):
        if self.output and self._output_generation==self._generation:
            dest=filedialog.asksaveasfilename(defaultextension='.png',filetypes=[('PNG','*.png')])
            if dest:
                if Path(dest).exists():messagebox.showerror('BlurFing','Choose a new filename; existing files are preserved.');return
                if Path(dest).resolve() in [Path(self.source).resolve(),Path(self.output).resolve()]:messagebox.showerror('BlurFing','Choose a new output path; source and audit outputs are preserved.');return
                shutil.copyfile(self.output,dest)
    def benchmark(self):
        if not self.source:return
        try:photo_arguments=self.photo_arguments()
        except ValueError as exc:messagebox.showerror('BlurFing',str(exc));return
        source=self.source
        def work():
            durations=[]
            for i in range(11):
                folder=str(Path(tempfile.mkdtemp(prefix='blurfing_gui_bench_'))/'result');t=time.perf_counter();r=self.execute('protect_fingerprint.py',['--input',source,'--output',folder,*photo_arguments]);dt=time.perf_counter()-t
                if i:durations.append(dict(seconds=dt,status=r['status'],transformed=r['fingerprints_transformed']))
            return dict(warmup=1,measurements=durations,scope='CLI wall-clock; includes interpreter/runtime startup; no matcher benchmark')
        self.job(work,lambda r:(self.text.delete('1.0','end'),self.text.insert('end',json.dumps(r,indent=2))))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo-engine',choices=['legacy','native_v12','distal_v13','pose_v14'],default='legacy')
    parser.add_argument('--photo-model',type=Path);parser.add_argument('--consumed-registry',type=Path)
    parser.add_argument('--development-replay',action='store_true');args=parser.parse_args()
    root=tk.Tk();App(root,photo_engine=args.photo_engine,photo_model=args.photo_model,
        consumed_registry=args.consumed_registry,development_replay=args.development_replay);root.mainloop()
