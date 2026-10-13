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
        for name,callback in [('Select image',self.select),('Process',self.process),('Runtime check',self.runtime),('Benchmark (1 + 10)',self.benchmark),('Save output',self.save)]:tk.Button(root,text=name,command=callback).pack(fill='x')
        self.label=tk.Label(root,text='PHOTO detector and production readiness remain unapproved.');self.label.pack();self.preview=tk.Label(root);self.preview.pack();self.text=tk.Text(root,width=90,height=15);self.text.pack()
    def select(self):self.source=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.bmp *.tif *.tiff')]);self.label.config(text=Path(self.source).name if self.source else 'No image selected')
    def execute(self,script,args):
        interpreter=os.environ.get('BLURFING_CORE_PYTHON') or sys.executable
        if Path(interpreter).name.lower()=='pythonw.exe':interpreter=str(Path(interpreter).with_name('python.exe'))
        if getattr(sys,'frozen',False) and not os.environ.get('BLURFING_CORE_PYTHON'):raise RuntimeError('Set BLURFING_CORE_PYTHON to the configured core Python executable')
        result=subprocess.run([interpreter,str(ROOT/'scripts'/script),*args],shell=False,capture_output=True,text=True,timeout=600);data=json.loads(result.stdout)
        if result.returncode or data.get('status')=='error':raise RuntimeError(data.get('error','CLI failure'))
        return data
    def job(self,work,complete):
        def run():
            try:value=work();self.root.after(0,lambda:complete(value))
            except Exception as exc:
                message=str(exc);self.root.after(0,lambda:messagebox.showerror('BlurFing',message))
        threading.Thread(target=run,daemon=True).start()
    def process(self):
        if not self.source:return
        source=self.source;folder=str(Path(tempfile.mkdtemp(prefix='blurfing_gui_'))/'result')
        def complete(data):
            self.output=data['output_path'];self.text.delete('1.0','end');self.text.insert('end',json.dumps(data,indent=2));image=ImageOps.exif_transpose(Image.open(self.output));image.thumbnail((900,550));self.photo=ImageTk.PhotoImage(image);self.preview.config(image=self.photo);self.label.config(text=f"{data['input_type']}: {data['status']} | detected {data['fingerprints_detected']}, transformed {data['fingerprints_transformed']}, rejected {data['fingerprints_rejected']}")
        self.job(lambda:self.execute('protect_fingerprint.py',['--input',source,'--output',folder]),complete)
    def runtime(self):self.job(lambda:self.execute('check_unified_runtime.py',[]),lambda r:(self.text.delete('1.0','end'),self.text.insert('end',json.dumps(r,indent=2))))
    def save(self):
        if self.output:
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
