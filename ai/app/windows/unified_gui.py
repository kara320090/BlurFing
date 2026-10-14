"""Thin Tk GUI for the common CLI. No detector/renderer code is duplicated."""
import json,subprocess,sys,tempfile,threading,shutil,time,os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox
from PIL import Image,ImageTk,ImageOps
ROOT=Path(__file__).resolve().parents[2]
class App:
    def __init__(self,root):
        self.root=root;root.title('BlurFing — development fail-closed pipeline');self.source=None;self.output=None;self.photo=None
        self._generation=0;self._output_generation=None;self._worker_lock=threading.Lock()
        for name,callback in [('Select image',self.select),('Process',self.process),('Runtime check',self.runtime),('Benchmark (1 + 10)',self.benchmark),('Save output',self.save)]:
            button=tk.Button(root,text=name,command=callback);button.pack(fill='x')
            if name=='Save output':self.save_button=button;button.config(state='disabled')
        self.label=tk.Label(root,text='PHOTO detector and production readiness remain unapproved.');self.label.pack();self.preview=tk.Label(root);self.preview.pack();self.text=tk.Text(root,width=90,height=15);self.text.pack()
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
        if result.returncode or data.get('status')=='error':raise RuntimeError(data.get('error','CLI failure'))
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
        source=self.source;generation=self.invalidate_result();folder=str(Path(tempfile.mkdtemp(prefix='blurfing_gui_'))/'result');self.label.config(text=f'Processing: {Path(source).name}')
        def complete(data):
            if generation!=self._generation or source!=self.source:return
            output=data['output_path']
            with Image.open(output) as image:
                preview=ImageOps.exif_transpose(image);preview.thumbnail((900,550));photo=ImageTk.PhotoImage(preview)
            self.output=output;self.photo=photo;self._output_generation=generation;self.text.delete('1.0','end');self.text.insert('end',json.dumps(data,indent=2));self.preview.config(image=self.photo);self.label.config(text=f"{data['input_type']}: {data['status']} | detected {data['fingerprints_detected']}, transformed {data['fingerprints_transformed']}, rejected {data['fingerprints_rejected']}");self.save_button.config(state='normal')
        self.job(lambda:self.execute('protect_fingerprint.py',['--input',source,'--output',folder]),complete)
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
        source=self.source
        def work():
            durations=[]
            for i in range(11):
                folder=str(Path(tempfile.mkdtemp(prefix='blurfing_gui_bench_'))/'result');t=time.perf_counter();r=self.execute('protect_fingerprint.py',['--input',source,'--output',folder]);dt=time.perf_counter()-t
                if i:durations.append(dict(seconds=dt,status=r['status'],transformed=r['fingerprints_transformed']))
            return dict(warmup=1,measurements=durations,scope='CLI wall-clock; includes interpreter/runtime startup; no matcher benchmark')
        self.job(work,lambda r:(self.text.delete('1.0','end'),self.text.insert('end',json.dumps(r,indent=2))))
if __name__=='__main__':root=tk.Tk();App(root);root.mainloop()
