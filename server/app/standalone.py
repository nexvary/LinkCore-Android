"""Independent panel deployment: existing LAN API plus personal Direct accounts."""
import json
import os
from contextlib import asynccontextmanager
from fastapi import Depends, HTTPException, Request
from . import main, legacy_direct

app = main.app
ADMIN_EMAIL = os.getenv('FGRCK_ADMIN_EMAIL', '').strip().lower()
if not ADMIN_EMAIL:
    raise RuntimeError('FGRCK_ADMIN_EMAIL is required for the independent panel')


def owner_guard(user=Depends(main.current_user)):
    if user.email.lower() != ADMIN_EMAIL:
        raise HTTPException(403, 'Administrator account required')
    return user


def legacy_log(db, action, *, detail=None, account_id=None):
    from sqlalchemy import select
    admin = db.scalar(select(main.User).where(main.User.email == ADMIN_EMAIL))
    main.audit(db, action, account_id or (admin.id if admin else None), detail=json.dumps(detail, ensure_ascii=False))

# Reuse the approved widgets and layout, using this deployment's owner JWT.
legacy_direct.WIDGET = legacy_direct.WIDGET.replace(
    "{credentials:'same-origin',...options}",
    "{credentials:'same-origin',...options,headers:{Authorization:'Bearer '+(sessionStorage.getItem('fgpanel_token')||''),...(options.headers||{})}}")
legacy_direct.USERS_WIDGET = legacy_direct.USERS_WIDGET.replace(
    "headers:body?{'Content-Type':'application/json'}:{}",
    "headers:{Authorization:'Bearer '+(sessionStorage.getItem('fgpanel_token')||''),...(body?{'Content-Type':'application/json'}:{})}")
legacy_direct.install(app, main.engine, main.SessionLocal, owner_guard, legacy_log)
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        legacy_direct.DirectBase.metadata.create_all(main.engine)
        monitor = app.state.fg_direct_email_monitor
        monitor.start()
        try:
            yield
        finally:
            monitor.stop()


app.router.lifespan_context = lifespan

@app.get('/panel/api/session')
def session(user=Depends(owner_guard)):
    return {'email': user.email, 'role': 'administrator'}

GATE = r'''<style>
body:not(.standalone-ready)>*:not(#standalone-auth):not(script):not(style){display:none!important}
#registerBtn{display:none!important}
#standalone-auth{max-width:460px;margin:8vh auto;padding:28px;background:#07100b;color:#79ff9d;border:1px solid #93aa9b;border-radius:18px;font:18px/1.8 Arial}
#standalone-auth input,#standalone-auth button{box-sizing:border-box;width:100%;padding:13px;margin:8px 0;background:#020705;color:#79ff9d;border:1px solid #93aa9b;border-radius:9px;font:inherit}
#standalone-tools{display:flex;gap:12px;margin-top:12px}
</style><script>
function standaloneBoot(){
 const auth=document.createElement('section');auth.id='standalone-auth';auth.dir='rtl';
 auth.innerHTML='<h1>FG Link</h1><p>تسجيل دخول الإدارة / Administrator sign in</p><form><label>البريد / Email<input type="email" autocomplete="username" required dir="ltr"></label><label>كلمة المرور / Password<input type="password" autocomplete="current-password" required dir="ltr"></label><button>دخول / Sign in</button></form><p role="status"></p>';
 document.body.append(auth);
 async function verify(){const token=sessionStorage.getItem('fgpanel_token');if(!token)return;
 const r=await fetch('/panel/api/session',{headers:{Authorization:'Bearer '+token}});
 if(r.ok){auth.remove();document.body.classList.add('standalone-ready')}else{sessionStorage.removeItem('fgpanel_token');auth.querySelector('[role=status]').textContent='يلزم حساب الإدارة / Administrator account required'}}
 auth.querySelector('form').onsubmit=async e=>{e.preventDefault();const inputs=auth.querySelectorAll('input'),b=auth.querySelector('button');b.disabled=true;
 try{const r=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:inputs[0].value,password:inputs[1].value})});const j=await r.json();if(!r.ok)throw Error('بيانات الدخول غير صحيحة / Invalid login');sessionStorage.setItem('fgpanel_token',j.access_token);location.reload()}
 catch(error){auth.querySelector('[role=status]').textContent=error.message;b.disabled=false}};
 const tools=document.createElement('div');tools.id='standalone-tools';
 tools.innerHTML='<button type="button">العربية / English</button><button type="button">خروج / Sign out</button>';
 tools.children[0].onclick=()=>toggleLang();tools.children[1].onclick=()=>{sessionStorage.removeItem('fgpanel_token');location.reload()};
 document.getElementById('fg-panel-header').append(tools);verify().catch(()=>{auth.querySelector('[role=status]').textContent='تعذر الاتصال / Connection unavailable'});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',standaloneBoot,{once:true});else standaloneBoot();
</script>'''

@app.middleware('http')
async def independent_panel(request: Request, call_next):
    if request.url.path == '/api/v1/auth/register':
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Public registration is disabled; use the administration panel'}, status_code=403)
    response = await call_next(request)
    if request.url.path == '/panel' and response.status_code == 200:
        from fastapi.responses import HTMLResponse
        body = b''.join([chunk async for chunk in response.body_iterator]).decode('utf-8')
        return HTMLResponse(body.replace('</body>', GATE + '</body>'), headers={'Cache-Control': 'no-store'})
    return response
