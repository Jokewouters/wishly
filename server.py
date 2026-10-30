#!/usr/bin/env python3
"""Wishly MVP: dependency-free local server, SQLite persistence and private reservations."""
import base64, hashlib, hmac, html, ipaddress, json, mimetypes, os, re, secrets, socket, sqlite3, threading, time, urllib.parse, urllib.request, urllib.error, math
from html.parser import HTMLParser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
STATIC = ROOT / 'static'
DB = Path(os.environ.get('WISHLY_DB', str(ROOT / 'wishly.sqlite3')))
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8765'))
LOCK = threading.Lock()
LIMIT_LOCK = threading.Lock()
LIMITS = {}
PRODUCTION = os.environ.get('WISHLY_ENV') == 'production'
PUBLIC_HOST = os.environ.get('WISHLY_PUBLIC_HOST', '').lower().strip()
FRONTEND_ORIGIN = os.environ.get('WISHLY_FRONTEND_ORIGIN', '').rstrip('/')
ENABLE_IMPORT = os.environ.get('WISHLY_ENABLE_IMPORT', '0' if PRODUCTION else '1') == '1'
ALLOW_REGISTRATION = os.environ.get('WISHLY_ALLOW_REGISTRATION', '1') == '1'

def rate_limit(key, max_hits, period):
    now=time.monotonic()
    with LIMIT_LOCK:
        # Do not retain unbounded arbitrary-client state forever.
        if len(LIMITS)>10000:
            for k,v in list(LIMITS.items()):
                if not v or v[-1] < now-period: LIMITS.pop(k,None)
        hits=[t for t in LIMITS.get(key,[]) if t > now-period]
        if len(hits)>=max_hits:
            LIMITS[key]=hits
            return False
        hits.append(now)
        LIMITS[key]=hits
        return True


def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def init_db():
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, salt TEXT NOT NULL, share_token TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', price REAL NOT NULL, category TEXT NOT NULL DEFAULT '', shop_url TEXT NOT NULL DEFAULT '', image TEXT NOT NULL DEFAULT '', received INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS reservations (item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE, guest_name TEXT NOT NULL, guest_key TEXT NOT NULL, created INTEGER NOT NULL);
        ''')

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 320000).hex()

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()

def json_bytes(obj): return json.dumps(obj, ensure_ascii=False).encode('utf-8')

def clean_item(item, public=False):
    result = {k: item[k] for k in ['id','title','description','price','category','shop_url','image','received','created']}
    result['received'] = bool(result['received'])
    return result

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.meta = {}; self.title = ''; self.in_title = False
        self.jsonld = []; self.in_jsonld = False; self.jsonld_parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or attrs.get('itemprop') or '').lower()
            if key:
                self.meta[key] = attrs.get('content','')
        if tag == 'title': self.in_title = True
        if tag == 'script' and attrs.get('type','').lower().startswith('application/ld+json'):
            self.in_jsonld = True; self.jsonld_parts = []
    def handle_data(self, data):
        if self.in_title: self.title += data
        if self.in_jsonld: self.jsonld_parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'script' and self.in_jsonld:
            self.in_jsonld = False
            try: self.jsonld.append(json.loads(''.join(self.jsonld_parts)))
            except (ValueError, TypeError): pass

def validate_web_url(url):
    parsed = urllib.parse.urlsplit(url)
    try: port = parsed.port
    except ValueError: port = -1
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or port not in (None,443):
        raise ValueError('Gebruik een geldige HTTPS-webshoplink.')
    try: ips = socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    except socket.gaierror: raise ValueError('De webshop is niet bereikbaar.')
    if not ips or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in ips):
        raise ValueError('Deze link is niet toegestaan.')

def nested_products(data):
    if isinstance(data,list):
        for item in data: yield from nested_products(item)
    elif isinstance(data,dict):
        types=data.get('@type',[])
        if isinstance(types,str): types=[types]
        if any(str(t).lower().split('/')[-1]=='product' for t in types): yield data
        for key in ('@graph','mainEntity','itemListElement'):
            if key in data: yield from nested_products(data[key])

def price_number(value):
    if value is None or isinstance(value,bool): return None
    value=str(value).replace('€','').replace('\u00a0','').replace(' ','').strip()
    if ',' in value and '.' in value:
        value=value.replace('.','').replace(',','.') if value.rfind(',')>value.rfind('.') else value.replace(',','')
    elif ',' in value: value=value.replace(',','.')
    try:
        number=float(value)
        return number if 0<=number<=1000000 else None
    except ValueError: return None

def remote_metadata(url):
    url=url.strip()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    opener=urllib.request.build_opener(NoRedirect)
    text=None
    for _ in range(5):
        validate_web_url(url)
        request=urllib.request.Request(url,headers={
            'User-Agent':'Mozilla/5.0 (compatible; WishlyGiftList/1.1)',
            'Accept':'text/html,application/xhtml+xml',
            'Accept-Language':'nl-BE,nl;q=0.9,en;q=0.7'})
        try:
            with opener.open(request,timeout=9) as response:
                if 'text/html' not in response.headers.get('Content-Type','').lower():
                    raise ValueError('Deze link bevat geen HTML-productpagina.')
                text=response.read(1_500_000).decode('utf-8',errors='replace')
                break
        except urllib.error.HTTPError as exc:
            if exc.code in (301,302,303,307,308):
                location=exc.headers.get('Location')
                if not location: raise ValueError('De webshop verwijst door zonder geldig adres.')
                url=urllib.parse.urljoin(url,location)
                continue
            if exc.code in (401,403,429):
                raise ValueError('De webshop blokkeert automatisch uitlezen. Voeg de gegevens handmatig toe of upload een screenshot.')
            raise ValueError('De webshop gaf een foutmelding (HTTP %s).'%exc.code)
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            raise ValueError('De webshop is niet bereikbaar vanuit Wishly. Controleer de link of vul de gegevens handmatig in.') from exc
    if text is None: raise ValueError('De webshop verwijst te vaak door.')
    parser=MetaParser();parser.feed(text)
    m=parser.meta
    product=next((p for doc in parser.jsonld for p in nested_products(doc)),{})
    offers=product.get('offers',{}) if isinstance(product,dict) else {}
    if isinstance(offers,list): offers=next((o for o in offers if isinstance(o,dict)),{})
    if not isinstance(offers,dict): offers={}
    image=product.get('image','')
    if isinstance(image,list): image=image[0] if image else ''
    if isinstance(image,dict): image=image.get('url','')
    image= image or m.get('og:image') or m.get('twitter:image') or m.get('image') or ''
    image=urllib.parse.urljoin(url,image) if isinstance(image,str) else ''
    if not image.startswith('https://'): image=''
    price=next((v for v in (
        price_number(offers.get('price')),
        price_number(offers.get('lowPrice')),
        price_number(m.get('product:price:amount')),
        price_number(m.get('og:price:amount')),
        price_number(m.get('price')),
    ) if v is not None),None)
    title=product.get('name') or m.get('og:title') or m.get('twitter:title') or parser.title
    description=product.get('description') or m.get('og:description') or m.get('description') or ''
    def clean(value,limit):
        return re.sub(r'\s+',' ',html.unescape(str(value))).strip()[:limit]
    title=clean(title,150); description=clean(description,1200)
    if not title and not image: raise ValueError('Deze pagina bevat geen herkenbare productinformatie.')
    return {'title':title,'description':description,'image':image,'price':price}

class Handler(BaseHTTPRequestHandler):
    server_version = 'Wishly/1.0'
    def log_message(self, fmt, *args): print('%s %s' % (self.address_string(),fmt % args))
    def safe_client(self):
        # Reverse proxy must enforce its own per-IP limits; do not trust forwarded IP headers.
        return self.client_address[0]
    def _security_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy', "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data:; connect-src 'self'; upgrade-insecure-requests" if PRODUCTION else "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data:; connect-src 'self'")
        if PRODUCTION: self.send_header('Strict-Transport-Security','max-age=31536000')
        if FRONTEND_ORIGIN and self.headers.get('Origin') == FRONTEND_ORIGIN:
            self.send_header('Access-Control-Allow-Origin',FRONTEND_ORIGIN)
            self.send_header('Access-Control-Allow-Credentials','true')
            self.send_header('Vary','Origin')
    def allowed_host(self):
        if not PRODUCTION: return True
        return bool(PUBLIC_HOST and self.headers.get('Host','').lower() == PUBLIC_HOST)
    def send(self, status, data, cookies=None):
        body = json_bytes(data)
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self._security_headers()
        if cookies: self.send_header('Set-Cookie',cookies)
        self.end_headers(); self.wfile.write(body)
    def cookie_string(self, token, maxage=2592000):
        secure = '; Secure' if PRODUCTION or os.environ.get('WISHLY_HTTPS') == '1' else ''
        return 'wishly_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age='+str(maxage)+secure
    def user(self, db):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        if 'wishly_session' not in cookie: return None
        token = cookie['wishly_session'].value
        return db.execute('SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires>?', (token_hash(token), int(time.time()))).fetchone()
    def content(self):
        size = int(self.headers.get('Content-Length','0'))
        if size < 1 or size > 5_000_000: raise ValueError('De afbeelding of aanvraag is te groot (maximum 3 MB per afbeelding).')
        try: return json.loads(self.rfile.read(size))
        except Exception: raise ValueError('Ongeldige gegevens.')
    def do_OPTIONS(self):
        if not self.allowed_host(): return self.send(400,{'error':'Ongeldige host.'})
        if self.headers.get('Origin') != FRONTEND_ORIGIN or not FRONTEND_ORIGIN:
            return self.send(403, {'error':'Ongeldige herkomst.'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin',FRONTEND_ORIGIN)
        self.send_header('Access-Control-Allow-Credentials','true')
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Access-Control-Max-Age','600')
        self.send_header('Vary','Origin')
        self.end_headers()

    def do_GET(self):
        if not self.allowed_host(): return self.send(400,{'error':'Ongeldige host.'})
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/api/'):
            try:
                with connect() as db:
                    u = self.user(db)
                    if path == '/api/me':
                        return self.send(200, {'user': {'email':u['email'],'share_token':u['share_token']} if u else None})
                    if path == '/api/items':
                        if not u: return self.send(401,{'error':'Log eerst in.'})
                        items = db.execute('SELECT * FROM items WHERE user_id=? ORDER BY created DESC,id DESC',(u['id'],)).fetchall()
                        return self.send(200,{'items':[clean_item(i) for i in items]})
                    match = re.fullmatch(r'/api/public/([A-Za-z0-9_-]{20,100})', path)
                    if match:
                        if not rate_limit(('public',self.safe_client()),120,60): return self.send(429,{'error':'Te veel aanvragen. Probeer later opnieuw.'})
                        owner = db.execute('SELECT id FROM users WHERE share_token=?',(match.group(1),)).fetchone()
                        if not owner: return self.send(404,{'error':'Verlanglijst niet gevonden.'})
                        items = db.execute('SELECT items.*, (reservations.item_id IS NOT NULL) AS reserved FROM items LEFT JOIN reservations ON reservations.item_id=items.id WHERE items.user_id=? AND items.received=0 ORDER BY items.created DESC,items.id DESC',(owner['id'],)).fetchall()
                        return self.send(200,{'items':[dict(clean_item(i),reserved=bool(i['reserved'])) for i in items]})
                    return self.send(404, {'error':'Niet gevonden.'})
            except Exception: return self.send(500, {'error':'Er liep iets mis.'})
        if path == '/' or re.fullmatch(r'/w/[A-Za-z0-9_-]{20,100}/?', path): path = '/index.html'
        target = (STATIC / path.lstrip('/')).resolve()
        if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
            self.send_error(404); return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(data)))
        self._security_headers()
        self.send_header('Cache-Control','no-store, max-age=0')
        self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if not self.allowed_host(): return self.send(400,{'error':'Ongeldige host.'})
        path = urllib.parse.urlparse(self.path).path
        # Browsers cannot submit cross-origin mutations using a valid JSON content type without preflight;
        # additionally reject foreign origins for requests with an Origin header.
        origin = self.headers.get('Origin')
        host = self.headers.get('Host','')
        if origin and origin != FRONTEND_ORIGIN and (urllib.parse.urlparse(origin).netloc.lower() != host.lower() or (PRODUCTION and urllib.parse.urlparse(origin).scheme != 'https')):
            return self.send(403,{'error':'Ongeldige herkomst.'})
        if PRODUCTION and not origin:
            return self.send(403,{'error':'Origin-header vereist.'})
        if 'application/json' not in self.headers.get('Content-Type',''):
            return self.send(415,{'error':'JSON vereist.'})
        try:
            data = self.content()
            with LOCK, connect() as db:
                if path in ('/api/register','/api/login'):
                    if not rate_limit(('auth',self.safe_client()),10,300): return self.send(429,{'error':'Te veel inlogpogingen. Probeer later opnieuw.'})
                    if path == '/api/register' and not ALLOW_REGISTRATION: return self.send(403,{'error':'Registreren is momenteel uitgeschakeld.'})
                    email = str(data.get('email','')).strip().lower()
                    password = str(data.get('password',''))
                    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(email)>200: raise ValueError('Vul een geldig e-mailadres in.')
                    if path == '/api/register':
                        if len(password)<10 or len(password)>200: raise ValueError('Kies een wachtwoord van minstens 10 tekens.')
                        salt=secrets.token_hex(16)
                        try:
                            cursor=db.execute('INSERT INTO users(email,password_hash,salt,share_token) VALUES (?,?,?,?)',(email,hash_password(password,salt),salt,secrets.token_urlsafe(30)))
                        except sqlite3.IntegrityError: return self.send(409,{'error':'Er bestaat al een account met dit e-mailadres.'})
                        uid=cursor.lastrowid
                    else:
                        u=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                        if not u or not hmac.compare_digest(hash_password(password,u['salt']),u['password_hash']): return self.send(401,{'error':'E-mailadres of wachtwoord onjuist.'})
                        uid=u['id']
                    token=secrets.token_urlsafe(32)
                    db.execute('INSERT INTO sessions VALUES (?,?,?)',(token_hash(token),uid,int(time.time())+2592000))
                    return self.send(200,{'ok':True},self.cookie_string(token))
                if path == '/api/logout':
                    cookie=SimpleCookie(); cookie.load(self.headers.get('Cookie',''))
                    if 'wishly_session' in cookie: db.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(cookie['wishly_session'].value),))
                    return self.send(200,{'ok':True},self.cookie_string('',0))
                match = re.fullmatch(r'/api/public/([A-Za-z0-9_-]{20,100})/reserve',path)
                if match:
                    if not rate_limit(('reserve',self.safe_client()),10,300): return self.send(429,{'error':'Te veel reserveringspogingen. Probeer later opnieuw.'})
                    owner=db.execute('SELECT id FROM users WHERE share_token=?',(match.group(1),)).fetchone()
                    if not owner: return self.send(404,{'error':'Lijst niet gevonden.'})
                    item_id = int(data.get('item_id',0)); name = str(data.get('name','')).strip()
                    if len(name)<2 or len(name)>80: raise ValueError('Vul je naam in (2 tot 80 tekens).')
                    item=db.execute('SELECT id FROM items WHERE id=? AND user_id=? AND received=0',(item_id,owner['id'])).fetchone()
                    if not item: return self.send(404,{'error':'Cadeau niet gevonden.'})
                    try: db.execute('INSERT INTO reservations VALUES (?,?,?,?)',(item_id,name,secrets.token_urlsafe(20),int(time.time())))
                    except sqlite3.IntegrityError: return self.send(409,{'error':'Dit cadeau is al gereserveerd.'})
                    return self.send(200,{'ok':True})
                u=self.user(db)
                if not u: return self.send(401,{'error':'Log eerst in.'})
                if path == '/api/metadata':
                    if not ENABLE_IMPORT: return self.send(403,{'error':'Automatisch ophalen is op deze server uitgeschakeld. Voeg een foto en gegevens handmatig toe.'})
                    if not rate_limit(('import',self.safe_client()),8,300): return self.send(429,{'error':'Te veel importpogingen. Probeer later opnieuw.'})
                    return self.send(200,remote_metadata(str(data.get('url',''))))
                if path == '/api/items/save':
                    title=str(data.get('title','')).strip()[:150]
                    if not title: raise ValueError('Geef het cadeau een naam.')
                    try: price=round(float(data.get('price',0)),2)
                    except Exception: raise ValueError('Vul een geldige prijs in.')
                    if not math.isfinite(price) or not 0<=price<=1000000: raise ValueError('Vul een geldige prijs in.')
                    image=str(data.get('image',''))
                    if image.startswith('data:'):
                        if not re.match(r'^data:image/(jpeg|png|webp|gif);base64,',image) or len(image)>4_200_000: raise ValueError('Gebruik een JPG, PNG of WebP van maximaal 3 MB.')
                    elif image and not image.startswith('https://'): raise ValueError('Gebruik een veilige afbeeldingslink.')
                    shop_url=str(data.get('shop_url','')).strip()[:2000]
                    if shop_url and (not shop_url.startswith('https://') or urllib.parse.urlsplit(shop_url).username or urllib.parse.urlsplit(shop_url).password or not urllib.parse.urlsplit(shop_url).hostname): raise ValueError('Gebruik een geldige HTTPS-webshoplink.')
                    category=str(data.get('category','Varia')).strip()
                    if category not in ('Tech','Koken','Interieur','Kledij','Varia'): raise ValueError('Kies een geldige categorie.')
                    values=(title,str(data.get('description',''))[:1500],price,category,shop_url,image,1 if data.get('received') else 0)
                    item_id=data.get('id')
                    if item_id:
                        result=db.execute('UPDATE items SET title=?,description=?,price=?,category=?,shop_url=?,image=?,received=? WHERE id=? AND user_id=?',(*values,int(item_id),u['id']))
                        if not result.rowcount: return self.send(404,{'error':'Cadeau niet gevonden.'})
                    else:
                        db.execute('INSERT INTO items(user_id,title,description,price,category,shop_url,image,received,created) VALUES (?,?,?,?,?,?,?,?,?)',(u['id'],*values,int(time.time())))
                    return self.send(200,{'ok':True})
                if path == '/api/items/delete':
                    db.execute('DELETE FROM items WHERE id=? AND user_id=?',(int(data.get('id',0)),u['id']))
                    return self.send(200,{'ok':True})
                return self.send(404,{'error':'Niet gevonden.'})
        except ValueError as e: return self.send(400,{'error':str(e)})
        except Exception as e:
            print('Error:',repr(e)); return self.send(500,{'error':'Er liep iets mis. Probeer opnieuw.'})

if __name__=='__main__':
    if PRODUCTION and (not PUBLIC_HOST or os.environ.get('WISHLY_HTTPS') != '1'):
        raise SystemExit('Productie vereist WISHLY_PUBLIC_HOST en WISHLY_HTTPS=1 achter een HTTPS reverse proxy.')
    init_db()
    print(f'Wishly is klaar op http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
