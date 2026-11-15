"""Explicit real-provider probe with a generated scene; never sends user photos."""
import base64,io,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from app import ai,explorer,speech
out=Path('docs/evidence/product-polish');out.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(640,480),'white');d=ImageDraw.Draw(image);d.rectangle((120,100,420,340),fill='green',outline='black',width=4);d.ellipse((450,200,540,290),fill='blue');b=io.BytesIO();image.save(b,format='JPEG');data='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
report={'source':'self-generated green rectangle and blue circle','vision_model':ai.settings().vision,'tts_model':ai.settings().tts,'results':[]}
for name,call in [('observe',lambda:explorer.observe({'image_data':data}))]:
 start=time.monotonic()
 try:
  result=call();text=result['description'];report['results'].append({'stage':name,'seconds':round(time.monotonic()-start,3),'ok':True,'description':text})
 except Exception as e:report['results'].append({'stage':name,'seconds':round(time.monotonic()-start,3),'ok':False,'code':getattr(e,'code',type(e).__name__)});text='A green rectangle is beside a blue circle.'
start=time.monotonic()
try:
 result=speech.handle({'action':'speak','text':text});raw=base64.b64decode(result['audio_data'].split(',')[1]);(out/('sample-voice.wav' if raw[:4]==b'RIFF' else 'sample-voice.mp3')).write_bytes(raw);report['results'].append({'stage':'speak','seconds':round(time.monotonic()-start,3),'ok':True,'bytes':len(raw)})
except Exception as e:report['results'].append({'stage':'speak','seconds':round(time.monotonic()-start,3),'ok':False,'code':getattr(e,'code',type(e).__name__)})
(out/'latency.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
