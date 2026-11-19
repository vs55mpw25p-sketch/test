"""Authenticated Internet Archive frame extractor; no private research data."""
import base64,hashlib,hmac,io,ipaddress,json,math,os,pathlib,socket,subprocess,tempfile,threading,time,urllib.parse,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PIL import Image,ImageOps
MAX_BYTES=150*1024*1024
LOCK=threading.Lock()
CACHE=tempfile.TemporaryDirectory(prefix="filmspuren-")
CACHED={}
def allowed_url(raw,initial=False):
    u=urllib.parse.urlsplit(raw);host=u.hostname or ''
    if u.scheme!='https' or u.username or u.password or u.port or not(host=='archive.org' or (not initial and host.endswith('.archive.org'))):raise ValueError('Only public Internet Archive URLs supported')
    if initial and (not u.path.startswith('/download/') or not u.path.lower().endswith(('.mp4','.webm')) or u.query or u.fragment):raise ValueError('Direct Archive video required')
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Non-public address blocked')
class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def download(url,path):
    allowed_url(url,True);deadline=time.monotonic()+20
    with urllib.request.build_opener(Redirects()).open(url,timeout=8) as r:
        if int(r.headers.get('Content-Length','0'))>MAX_BYTES:raise ValueError('Video exceeds 150 MiB')
        count=0
        with path.open('wb') as f:
            while True:
                if time.monotonic()>deadline:raise ValueError('Download deadline exceeded')
                block=r.read(1024*1024)
                if not block:break
                count+=len(block)
                if count>MAX_BYTES:raise ValueError('Video exceeds 150 MiB')
                f.write(block)
def extract_file(path,t):
    opts=['-protocol_whitelist','file,pipe']
    p=subprocess.run(['ffprobe','-v','error',*opts,'-show_entries','format=duration','-of','json',str(path)],capture_output=True,timeout=5,check=True)
    duration=float(json.loads(p.stdout)['format']['duration'])
    if not math.isfinite(duration) or not 0<duration<=86400:raise ValueError('Invalid duration')
    if t>=duration:return {'duration':duration,'eof':True}
    p=subprocess.run(['ffmpeg','-v','error','-threads','1',*opts,'-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=384:-2','-f','image2pipe','-vcodec','mjpeg','pipe:1'],capture_output=True,timeout=12,check=True)
    image=Image.open(io.BytesIO(p.stdout)).convert('RGB');image.thumbnail((384,384))
    hashes=[];variance=0
    for i,im in enumerate([image,ImageOps.mirror(image),image.crop((round(image.width*.1),round(image.height*.1),round(image.width*.9),round(image.height*.9)))]):
        gray=[r*.299+g*.587+b*.114 for r,g,b in im.resize((9,8),Image.Resampling.BILINEAR).getdata()]
        bits=''.join('1' if gray[y*9+x]>gray[y*9+x+1] else '0' for y in range(8) for x in range(8))
        hashes.append(f'{int(bits,2):016x}')
        if i==0:
            mean=sum(gray)/72;variance=sum((x-mean)**2 for x in gray)/72
    out=io.BytesIO();image.save(out,format='JPEG',quality=65)
    return {'time':t,'duration':duration,'hashes':hashes,'variance':variance,'image':'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def setup(self):
        super().setup();self.connection.settimeout(10)
    def reply(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.reply(200,{'status':'ok'}) if self.path=='/health' else self.reply(404,{'error':'Not found'})
    def do_POST(self):
        token=os.environ.get('VIDEO_EXTRACTOR_TOKEN','')
        if len(token)<32 or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):self.reply(401,{'error':'Unauthorized'});return
        if self.path!='/extract':self.reply(404,{'error':'Not found'});return
        if not LOCK.acquire(False):self.reply(429,{'error':'Worker busy'});return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=4096:raise ValueError('Invalid request length')
            body=json.loads(self.rfile.read(n));t=body['time']
            if isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or not 0<=t<=86400:raise ValueError('Invalid timestamp')
            path=pathlib.Path(CACHE.name)/'video'
            if CACHED.get('url')!=body['url'] or time.monotonic()-CACHED.get('at',0)>3600 or not path.exists():
                CACHED.clear();path.unlink(missing_ok=True)
                try:download(body['url'],path)
                except Exception:path.unlink(missing_ok=True);raise
                with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
                CACHED.update(url=body['url'],at=time.monotonic(),digest=digest)
            out=extract_file(path,t);out['contentHash']=CACHED['digest'];self.reply(200,out)
        except ValueError as e:self.reply(422,{'error':str(e)})
        except Exception:self.reply(502,{'error':'Video extraction failed or timed out'})
        finally:LOCK.release()
if __name__=='__main__':
    if len(os.environ.get('VIDEO_EXTRACTOR_TOKEN',''))<32:raise SystemExit('VIDEO_EXTRACTOR_TOKEN must have at least 32 characters')
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
