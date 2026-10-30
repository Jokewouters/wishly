// Optionele Supabase Edge Function. Gebruik uitsluitend een kleine lijst vertrouwde webshops.
// Vereist een geldige gebruikers-JWT bij de standaard Supabase Edge Function-configuratie.
const cors = {"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"authorization, x-client-info, apikey, content-type","Access-Control-Allow-Methods":"POST, OPTIONS"};
const allowed = ["coolblue.be","bol.com","ikea.com","mediamarkt.be","fnac.be","amazon.com","amazon.de","amazon.nl"];
const out=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{...cors,"Content-Type":"application/json"}});
function validDomain(host:string){return allowed.some(d=>host===d||host.endsWith('.'+d));}
function meta(html:string,key:string){const escaped=key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); const patterns=[new RegExp(`<meta\\s+[^>]*?(?:property|name)=["']${escaped}["'][^>]*?content=["']([^"']*)["']`,'i'),new RegExp(`<meta\\s+[^>]*?content=["']([^"']*)["'][^>]*?(?:property|name)=["']${escaped}["']`,'i')];for(const p of patterns){const m=html.match(p);if(m)return m[1].replaceAll('&amp;','&').replaceAll('&quot;','"')}return ''}
Deno.serve(async req=>{
 if(req.method==='OPTIONS')return new Response(null,{headers:cors});
 if(req.method!=='POST')return out({error:'Method not allowed'},405);
 try{
 const {url}=await req.json();const target=new URL(String(url));
 if(target.protocol!=='https:'||!validDomain(target.hostname.toLowerCase())||target.username||target.password||target.port)return out({error:'Webshop niet ondersteund'},400);
 const resp=await fetch(target.toString(),{redirect:'manual',signal:AbortSignal.timeout(6000),headers:{'Accept':'text/html','User-Agent':'WishlyLinkPreview/1.0'}});
 if(!resp.ok||!resp.headers.get('content-type')?.includes('text/html'))return out({error:'Webshop laat uitlezen niet toe'},422);
 const len=Number(resp.headers.get('content-length')||0);if(len>750000)return out({error:'Pagina te groot'},422);
 const body=(await resp.text()).slice(0,750000);
 let title=meta(body,'og:title')||meta(body,'twitter:title')||body.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1]||'';
 let description=meta(body,'og:description')||meta(body,'description');
 let image=meta(body,'og:image')||meta(body,'twitter:image');
 let price=meta(body,'product:price:amount')||meta(body,'og:price:amount');
 const scripts=[...body.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)].slice(0,20);
 function findProduct(value:any):any{if(Array.isArray(value)){for(const n of value){const f=findProduct(n);if(f)return f;}return null}if(!value||typeof value!=='object')return null;if(String(value['@type']||'').toLowerCase().includes('product'))return value;return findProduct(value['@graph']||[])}
 for(const m of scripts){try{const p=findProduct(JSON.parse(m[1]));if(p){title=String(p.name||title);description=String(p.description||description);image=String((Array.isArray(p.image)?p.image[0]:p.image)||image);const offer=Array.isArray(p.offers)?p.offers[0]:p.offers;price=String(offer?.price||price);break}}catch{}}
 const n=price.trim()?Number(String(price).replace(',','.')):NaN;const photo=image?new URL(image,target).href:'';
 return out({title:title.slice(0,150),description:description.replace(/<[^>]*>/g,'').slice(0,1500),image:photo.startsWith('https://')?photo:'',price:Number.isFinite(n)&&n>=0?n:null});
 }catch{return out({error:'Kon productinformatie niet ophalen'},422)}
});
