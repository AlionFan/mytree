"""Private original-image archive. Ownership is supplied by authenticated transport."""
import base64,hashlib,io,os,re,sqlite3,uuid,warnings
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
from PIL import Image,ImageOps,UnidentifiedImageError
from . import profile
from .errors import DomainError
MAX_BYTES=10*1024*1024
KINDS={'JPEG':('image/jpeg','jpg'),'PNG':('image/png','png'),'WEBP':('image/webp','webp'),'GIF':('image/gif','gif'),'BMP':('image/bmp','bmp')}

def _id(value):
 if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):raise DomainError('INVALID_UPLOAD','上传记录编号不正确。')
 return value

@contextmanager
def _db():
 path=Path(profile._PATH).resolve().parent/'uploads.sqlite3'
 path.parent.mkdir(parents=True,exist_ok=True)
 try:
  con=sqlite3.connect(str(path),timeout=15);os.chmod(path,0o600);con.row_factory=sqlite3.Row
  con.execute('PRAGMA secure_delete=ON')
  con.execute('CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY,owner TEXT NOT NULL,request_id TEXT NOT NULL,digest TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,extension TEXT NOT NULL,created_at TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,size INTEGER NOT NULL,original BLOB NOT NULL,thumbnail BLOB NOT NULL,UNIQUE(owner,request_id))')
  con.execute('CREATE INDEX IF NOT EXISTS uploads_owner ON uploads(owner,created_at DESC)')
  with con:yield con
 except (sqlite3.Error,OSError):raise DomainError('UPLOAD_STORAGE_FAILED','上传记录暂时无法保存或读取，请稍后重试。',503) from None
 finally:
  if 'con' in locals():con.close()

def save(owner,body):
 _id(owner);request=_id(body.get('request_id'));data=body.get('image_data');name=body.get('name','图片')
 if not isinstance(name,str) or not name.strip() or len(name)>240 or re.search(r'[\x00-\x1f\x7f]',name):raise DomainError('INVALID_UPLOAD','文件名不正确。')
 if not isinstance(data,str) or len(data)>14_000_000 or not re.match(r'^data:image/[a-zA-Z0-9.+-]+;base64,',data):raise DomainError('INVALID_IMAGE','请选择不超过10 MB的图片。')
 try:raw=base64.b64decode(data.split(',',1)[1],validate=True)
 except (ValueError,TypeError):raise DomainError('INVALID_IMAGE','图片数据不完整。') from None
 if not raw or len(raw)>MAX_BYTES:raise DomainError('PAYLOAD_TOO_LARGE','图片请小于10 MB。',413)
 digest=hashlib.sha256(raw).hexdigest()
 with _db() as db:
  old=db.execute('SELECT * FROM uploads WHERE owner=? AND request_id=?',(owner,request)).fetchone()
  if old:
   if old['digest']!=digest or old['name']!=name:raise DomainError('CONFLICT','同一次上传的图片已变化，请重新选择。',409)
   return {'ok':True,'upload':_public(old),'duplicate':True}
 try:
  with warnings.catch_warnings():
   warnings.simplefilter('error',Image.DecompressionBombWarning)
   with Image.open(io.BytesIO(raw)) as image:
    if image.format not in KINDS or image.width*image.height>40_000_000:raise ValueError()
    kind=image.format;image.verify()
   with Image.open(io.BytesIO(raw)) as image:
    image=ImageOps.exif_transpose(image);width,height=image.size
    image.thumbnail((400,400));canvas=Image.new('RGB',image.size,'white')
    if image.mode in ('RGBA','LA'):
     rgba=image.convert('RGBA');canvas.paste(rgba,mask=rgba.getchannel('A'))
    else:canvas.paste(image.convert('RGB'))
    output=io.BytesIO();canvas.save(output,format='JPEG',quality=82);thumb=output.getvalue()
 except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombWarning,Image.DecompressionBombError):raise DomainError('INVALID_IMAGE','图片无法打开，请换一张JPG、PNG或WebP图片。') from None
 identifier=uuid.uuid4().hex;mime,extension=KINDS[kind];created=datetime.now(timezone.utc).isoformat()
 with _db() as db:
  # Concurrent same-request uploads converge to a single durable row.
  db.execute('INSERT OR IGNORE INTO uploads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,owner,request,digest,name,mime,extension,created,width,height,len(raw),raw,thumb))
  row=db.execute('SELECT * FROM uploads WHERE owner=? AND request_id=?',(owner,request)).fetchone()
  if row['digest']!=digest or row['name']!=name:raise DomainError('CONFLICT','同一次上传的图片已变化，请重新选择。',409)
  return {'ok':True,'upload':_public(row),'duplicate':row['id']!=identifier}

def _public(row):
 return {key:row[key] for key in ('id','name','mime','created_at','width','height','size')}|{'image_url':'/api/uploads/'+row['id']+'/image','thumbnail_url':'/api/uploads/'+row['id']+'/thumb'}

def listing(owner,page=1):
 _id(owner)
 try:page=int(page)
 except (ValueError,TypeError):raise DomainError('INVALID_PAGE','页码不正确。') from None
 if not 1<=page<=100000:raise DomainError('INVALID_PAGE','页码不正确。')
 with _db() as db:
  total=db.execute('SELECT COUNT(*) FROM uploads WHERE owner=?',(owner,)).fetchone()[0]
  rows=db.execute('SELECT id,name,mime,created_at,width,height,size FROM uploads WHERE owner=? ORDER BY created_at DESC,id DESC LIMIT 30 OFFSET ?',(owner,(page-1)*30)).fetchall()
  return {'ok':True,'items':[_public(v) for v in rows],'page':page,'total':total,'has_more':page*30<total}

def image(owner,identifier,thumbnail=False):
 _id(owner);_id(identifier)
 with _db() as db:
  row=db.execute('SELECT thumbnail,original,mime,extension FROM uploads WHERE owner=? AND id=?',(owner,identifier)).fetchone()
  if not row:raise DomainError('UPLOAD_NOT_FOUND','没有找到这张图片。',404)
  return (bytes(row['thumbnail']),'image/jpeg','jpg') if thumbnail else (bytes(row['original']),row['mime'],row['extension'])

def delete(owner,body):
 _id(owner);identifier=_id(body.get('upload_id'))
 with _db() as db:
  count=db.execute('DELETE FROM uploads WHERE owner=? AND id=?',(owner,identifier)).rowcount
  if not count:raise DomainError('UPLOAD_NOT_FOUND','没有找到这张图片。',404)
 return {'ok':True}
