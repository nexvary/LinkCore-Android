from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)

PANEL_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#07131c">
  <title>FG Machines Link — Cloud Panel</title>
  <style>
    :root{--bg:#050d13;--panel:#0c1d29;--panel2:#102735;--line:#365263;--text:#eef7fb;--muted:#8da3af;--cyan:#20d8ee;--green:#50e39c;--red:#ff5d68;--gold:#e3aa4b;--purple:#a77df5}
    *{box-sizing:border-box}html,body{margin:0;background:radial-gradient(circle at 85% 0,#0b2b38 0,#050d13 38%,#03090d 100%);color:var(--text);font-family:Tahoma,Arial,sans-serif;min-height:100%}
    button,input,select{font:inherit}.shell{max-width:1380px;margin:auto;padding:18px}.top{display:flex;gap:14px;align-items:center;justify-content:space-between;border:1px solid #76909e;border-radius:26px;padding:16px 20px;background:linear-gradient(135deg,#0d2330,#07131c)}
    .brand{display:flex;align-items:center;gap:14px}.logo{width:58px;height:58px;border-radius:50%;border:4px solid var(--cyan);display:grid;place-items:center;font-weight:900;font-size:27px;color:var(--green);box-shadow:0 0 22px #20d8ee33}.brand h1{margin:0;font-size:24px}.brand p{margin:4px 0 0;color:var(--green)}
    .actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--line);background:#0b1b25;color:var(--text);border-radius:13px;padding:10px 14px;cursor:pointer}.btn:hover{border-color:var(--cyan)}.btn.primary{background:#0c5570;border-color:var(--cyan)}.btn.green{background:#124d39;border-color:var(--green)}.btn.red{background:#4d1820;border-color:var(--red)}.btn.gold{background:#4a3518;border-color:var(--gold)}.btn:disabled{opacity:.38;cursor:not-allowed}
    .auth{max-width:520px;margin:70px auto 0;border:1px solid var(--line);border-radius:24px;padding:24px;background:#091923e8;box-shadow:0 20px 70px #0008}.auth h2{margin:0 0 8px;color:var(--cyan)}.auth p{color:var(--muted);line-height:1.7}.field{display:grid;gap:6px;margin:12px 0}.field label{color:#b7cad4;font-size:13px}.field input,.field select{width:100%;background:#061219;border:1px solid #385365;color:var(--text);border-radius:12px;padding:12px;outline:none}.field input:focus,.field select:focus{border-color:var(--cyan);box-shadow:0 0 0 3px #20d8ee1a}
    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;margin-top:16px}.card{background:linear-gradient(145deg,#0b1c27,#07131b);border:1px solid #2d4858;border-radius:20px;padding:16px;box-shadow:0 12px 35px #0004}.stats{grid-column:span 3}.wide{grid-column:span 8}.side{grid-column:span 4}.full{grid-column:1/-1}.card h2,.card h3{margin:0 0 10px}.card h2{color:var(--cyan)}.metric{font-size:28px;font-weight:800}.muted{color:var(--muted)}.ok{color:var(--green)}.bad{color:var(--red)}.gold{color:var(--gold)}
    .deviceGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.device{border:2px solid #385463;border-radius:18px;padding:14px;background:#0c202b}.device.online{border-color:var(--green)}.device.offline{border-color:#6f4750}.deviceHead{display:flex;justify-content:space-between;gap:12px;align-items:start}.device h3{margin:0;font-size:18px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:#718895}.pill{display:inline-block;border:1px solid #426070;border-radius:99px;padding:4px 9px;font-size:11px}.outlets{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:12px}.outlet{border:1px solid #365365;border-radius:13px;padding:9px 4px;text-align:center}.outlet strong{display:block;margin-bottom:7px}.outlet.denied{opacity:.3}
    .split{display:grid;grid-template-columns:1fr 1fr;gap:12px}.notice{border:1px solid #446070;border-radius:14px;padding:10px 12px;color:#b8cbd5;background:#07151d;margin:10px 0;white-space:pre-wrap}.secret{border-color:var(--gold);color:#ffe0a1}.hidden{display:none!important}
    dialog{width:min(820px,94vw);max-height:88vh;overflow:auto;background:#081720;color:var(--text);border:1px solid #547080;border-radius:22px;padding:0}dialog::backdrop{background:#000b}.modalHead{position:sticky;top:0;background:#0b1d27;padding:15px 18px;border-bottom:1px solid #314c5a;display:flex;justify-content:space-between;align-items:center}.modalBody{padding:16px}.share{border:1px solid #314d5b;border-radius:15px;padding:12px;margin:9px 0}.checks{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.checks label{border:1px solid #3b5868;border-radius:10px;padding:7px 10px}.toast{position:fixed;inset-inline-start:18px;bottom:18px;max-width:520px;background:#0d2430;border:1px solid var(--cyan);border-radius:14px;padding:12px 16px;box-shadow:0 15px 40px #0008;z-index:30}
    @media(max-width:900px){.stats{grid-column:span 6}.wide,.side{grid-column:1/-1}.deviceGrid{grid-template-columns:1fr}.top{align-items:flex-start}.split{grid-template-columns:1fr}}
    @media(max-width:520px){.shell{padding:9px}.top{border-radius:20px;padding:12px}.brand h1{font-size:18px}.brand p{font-size:12px}.logo{width:48px;height:48px}.stats{grid-column:1/-1}.outlets{grid-template-columns:repeat(2,1fr)}}
  </style>
</head>
<body>
<div class="shell">
  <header class="top">
    <div class="brand"><div class="logo">FG</div><div><h1>FG Machines Link</h1><p id="subTitle">لوحة التحكم السحابية الآمنة</p></div></div>
    <div class="actions">
      <button class="btn" id="langBtn" onclick="toggleLang()">English</button>
      <button class="btn" id="docsBtn" onclick="location.href='/docs'">API Docs</button>
      <button class="btn red hidden" id="logoutBtn" onclick="logout()">تسجيل الخروج</button>
    </div>
  </header>

  <section id="authView" class="auth">
    <h2 id="authTitle">تسجيل الدخول إلى الخادم</h2>
    <p id="authText">استخدم حساب FG Link. رمز الجلسة يبقى داخل هذه الصفحة فقط ويُمسح عند إغلاق المتصفح.</p>
    <div class="field"><label id="emailLabel">البريد الإلكتروني</label><input id="email" type="email" autocomplete="username"></div>
    <div class="field"><label id="passwordLabel">كلمة المرور</label><input id="password" type="password" autocomplete="current-password"></div>
    <div class="actions">
      <button class="btn primary" id="loginBtn" onclick="login()">دخول</button>
      <button class="btn" id="registerBtn" onclick="registerAccount()">إنشاء حساب جديد</button>
    </div>
    <div id="authMsg" class="notice hidden"></div>
  </section>

  <main id="dashboard" class="hidden">
    <div class="grid">
      <section class="card stats"><div class="muted" id="statServerLabel">الخادم</div><div class="metric ok" id="serverState">...</div></section>
      <section class="card stats"><div class="muted" id="statDevicesLabel">الأجهزة</div><div class="metric" id="deviceCount">0</div></section>
      <section class="card stats"><div class="muted" id="statOnlineLabel">متصل الآن</div><div class="metric ok" id="onlineCount">0</div></section>
      <section class="card stats"><div class="muted" id="statVersionLabel">الإصدار</div><div class="metric gold">0.2</div></section>

      <section class="card wide">
        <div class="deviceHead"><div><h2 id="devicesTitle">الأجهزة والمشتركون</h2><div class="muted" id="devicesHint">التحكم يظهر فقط للمخارج المسموح بها للحساب.</div></div><button class="btn" onclick="refreshAll()">تحديث</button></div>
        <div id="deviceGrid" class="deviceGrid"></div>
      </section>

      <section class="card side">
        <h2 id="setupTitle">إعداد الخادم</h2>
        <div class="field"><label id="controllerNameLabel">اسم Controller</label><input id="controllerName" value="FG Link Android Controller"></div>
        <button class="btn green" id="createControllerBtn" onclick="createController()">إنشاء Controller</button>
        <div id="controllerResult" class="notice secret hidden"></div>
        <hr style="border:0;border-top:1px solid #294553;margin:18px 0">
        <h3 id="registerDeviceTitle">تسجيل جهاز MTTL</h3>
        <div class="field"><label>Controller ID</label><input id="controllerId"></div>
        <div class="field"><label>MAC</label><input id="deviceMac" placeholder="AABBCCDDEEFF"></div>
        <div class="split">
          <div class="field"><label id="deviceNameLabel">اسم الجهاز</label><input id="deviceName" placeholder="MTTL-W01"></div>
          <div class="field"><label id="roomLabel">الغرفة</label><input id="deviceRoom"></div>
        </div>
        <div class="field"><label>Firmware</label><input id="deviceFirmware"></div>
        <button class="btn primary" id="registerDeviceBtn" onclick="registerDevice()">تسجيل الجهاز</button>
      </section>
    </div>
  </main>
</div>

<dialog id="shareDialog">
  <div class="modalHead"><strong id="shareTitle">إدارة المشتركين والمخارج</strong><button class="btn" onclick="closeShares()">×</button></div>
  <div class="modalBody">
    <div id="shareDevice" class="notice"></div>
    <div class="split">
      <div class="field"><label id="inviteRoleLabel">صلاحية الدعوة</label><select id="inviteRole"><option value="view">View</option><option value="control" selected>Control</option><option value="admin">Admin</option></select></div>
      <div class="field"><label id="inviteHoursLabel">مدة الدعوة بالساعات</label><input id="inviteHours" type="number" value="72" min="1" max="720"></div>
    </div>
    <button class="btn green" id="createInviteBtn" onclick="createInvite()">إنشاء كود مشاركة</button>
    <div id="inviteResult" class="notice secret hidden"></div>
    <div id="sharesList"></div>
  </div>
</dialog>

<div id="toast" class="toast hidden"></div>

<script>
const T={
 ar:{dir:"rtl",langBtn:"English",sub:"لوحة التحكم السحابية الآمنة",logout:"تسجيل الخروج",authTitle:"تسجيل الدخول إلى الخادم",authText:"استخدم حساب FG Link. رمز الجلسة يبقى داخل هذه الصفحة فقط ويُمسح عند إغلاق المتصفح.",email:"البريد الإلكتروني",password:"كلمة المرور",login:"دخول",register:"إنشاء حساب جديد",server:"الخادم",devices:"الأجهزة",online:"متصل الآن",version:"الإصدار",devicesTitle:"الأجهزة والمشتركون",devicesHint:"التحكم يظهر فقط للمخارج المسموح بها للحساب.",setup:"إعداد الخادم",controllerName:"اسم Controller",createController:"إنشاء Controller",registerDevice:"تسجيل جهاز MTTL",deviceName:"اسم الجهاز",room:"الغرفة",saveDevice:"تسجيل الجهاز",shares:"إدارة المشتركين والمخارج",inviteRole:"صلاحية الدعوة",inviteHours:"مدة الدعوة بالساعات",createInvite:"إنشاء كود مشاركة",connected:"متصل",offline:"غير متصل",manage:"المشتركون",on:"تشغيل",off:"إيقاف",outlet:"مخرج",noDevices:"لا توجد أجهزة مسجلة.",owner:"مالك",control:"تحكم",admin:"مدير",view:"مشاهدة",save:"حفظ المخارج",legacy:"غير مقسّم بعد: كل المخارج متاحة حسب الصلاحية."},
 en:{dir:"ltr",langBtn:"العربية",sub:"Secure Cloud Control Panel",logout:"Sign out",authTitle:"Sign in to server",authText:"Use your FG Link account. The session token stays in this tab and is cleared when the browser session ends.",email:"Email",password:"Password",login:"Sign in",register:"Create account",server:"Server",devices:"Devices",online:"Online now",version:"Version",devicesTitle:"Devices & subscribers",devicesHint:"Outlet controls are shown only when the account is authorized.",setup:"Server setup",controllerName:"Controller name",createController:"Create controller",registerDevice:"Register MTTL device",deviceName:"Device name",room:"Room",saveDevice:"Register device",shares:"Subscribers & outlet access",inviteRole:"Invite role",inviteHours:"Invite lifetime (hours)",createInvite:"Create share code",connected:"Online",offline:"Offline",manage:"Subscribers",on:"ON",off:"OFF",outlet:"Outlet",noDevices:"No devices registered.",owner:"Owner",control:"Control",admin:"Admin",view:"View",save:"Save outlets",legacy:"Not split yet: role defaults apply."}
};
let lang=localStorage.getItem("fgpanel_lang")||"ar";
let token=sessionStorage.getItem("fgpanel_token")||"";
let devices=[],activeMac="";

function tr(k){return (T[lang]&&T[lang][k])||k}
function esc(v){return String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]))}
function applyLang(){
 document.documentElement.lang=lang;document.documentElement.dir=T[lang].dir;
 const map={langBtn:"langBtn",subTitle:"sub",logoutBtn:"logout",authTitle:"authTitle",authText:"authText",emailLabel:"email",passwordLabel:"password",loginBtn:"login",registerBtn:"register",statServerLabel:"server",statDevicesLabel:"devices",statOnlineLabel:"online",statVersionLabel:"version",devicesTitle:"devicesTitle",devicesHint:"devicesHint",setupTitle:"setup",controllerNameLabel:"controllerName",createControllerBtn:"createController",registerDeviceTitle:"registerDevice",deviceNameLabel:"deviceName",roomLabel:"room",registerDeviceBtn:"saveDevice",shareTitle:"shares",inviteRoleLabel:"inviteRole",inviteHoursLabel:"inviteHours",createInviteBtn:"createInvite"};
 for(const [id,key] of Object.entries(map)){const e=document.getElementById(id);if(e)e.textContent=tr(key)}
 renderDevices();
}
function toggleLang(){lang=lang==="ar"?"en":"ar";localStorage.setItem("fgpanel_lang",lang);applyLang()}
function toast(msg,bad=false){const e=document.getElementById("toast");e.textContent=msg;e.style.borderColor=bad?"var(--red)":"var(--cyan)";e.classList.remove("hidden");setTimeout(()=>e.classList.add("hidden"),4200)}
async function api(path,opts={}){
 const headers={"Content-Type":"application/json",...(opts.headers||{})};if(token)headers.Authorization="Bearer "+token;
 const r=await fetch(path,{...opts,headers});let data={};try{data=await r.json()}catch(_){}
 if(!r.ok){if(r.status===401&&token){logout();}throw new Error(data.detail||("HTTP "+r.status))}
 return data
}
function showDashboard(){document.getElementById("authView").classList.add("hidden");document.getElementById("dashboard").classList.remove("hidden");document.getElementById("logoutBtn").classList.remove("hidden")}
function showAuth(){document.getElementById("authView").classList.remove("hidden");document.getElementById("dashboard").classList.add("hidden");document.getElementById("logoutBtn").classList.add("hidden")}
async function login(){
 try{const d=await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email:email.value,password:password.value})});token=d.access_token;sessionStorage.setItem("fgpanel_token",token);showDashboard();await refreshAll()}catch(e){authError(e.message)}
}
async function registerAccount(){
 try{const d=await api("/api/v1/auth/register",{method:"POST",body:JSON.stringify({email:email.value,password:password.value})});token=d.access_token;sessionStorage.setItem("fgpanel_token",token);showDashboard();await refreshAll()}catch(e){authError(e.message)}
}
function authError(m){const e=document.getElementById("authMsg");e.textContent=m;e.classList.remove("hidden")}
function logout(){token="";sessionStorage.removeItem("fgpanel_token");showAuth()}
async function refreshAll(){
 try{
  const [h,d]=await Promise.all([api("/healthz"),api("/api/v1/devices")]);devices=d.devices||[];
  serverState.textContent=h.ok?"ONLINE":"ERROR";serverState.className="metric "+(h.ok?"ok":"bad");
  deviceCount.textContent=devices.length;onlineCount.textContent=devices.filter(x=>x.connected).length;renderDevices()
 }catch(e){toast(e.message,true)}
}
function roleLabel(r){return tr(r)||r}
function renderDevices(){
 const g=document.getElementById("deviceGrid");if(!g)return;
 if(!devices.length){g.innerHTML='<div class="notice">'+tr("noDevices")+'</div>';return}
 g.innerHTML=devices.map(d=>{
  const allowed=new Set(d.allowed_outlets||[]);
  const outs=[1,2,3,4].map(n=>'<div class="outlet '+(allowed.has(n)?"":"denied")+'"><strong>'+tr("outlet")+" "+n+'</strong><button class="btn green" '+(allowed.has(n)?"":"disabled")+' onclick="setOutlet(\''+d.mac+'\','+n+',\'on\')">'+tr("on")+'</button> <button class="btn red" '+(allowed.has(n)?"":"disabled")+' onclick="setOutlet(\''+d.mac+'\','+n+',\'off\')">'+tr("off")+'</button></div>').join("");
  const canAdmin=d.role==="owner"||d.role==="admin";
  return '<article class="device '+(d.connected?"online":"offline")+'"><div class="deviceHead"><div><h3>'+esc(d.name||"MTTL-W01")+'</h3><div class="muted">'+esc(d.room||"—")+'</div><div class="mono">'+esc(d.mac)+'</div></div><div><span class="pill '+(d.connected?"ok":"bad")+'">'+(d.connected?tr("connected"):tr("offline"))+'</span><br><span class="pill" style="margin-top:6px">'+esc(roleLabel(d.role))+'</span></div></div><div class="outlets">'+outs+'</div>'+(canAdmin?'<button class="btn" style="margin-top:10px" onclick="openShares(\''+d.mac+'\')">'+tr("manage")+'</button>':"")+'</article>'
 }).join("")
}
async function setOutlet(mac,n,state){try{await api("/api/v1/devices/"+mac+"/outlets/"+n+"?state="+state,{method:"POST"});toast("OK · "+mac+" · "+n+" · "+state)}catch(e){toast(e.message,true)}}
async function createController(){
 try{const d=await api("/api/v1/controllers",{method:"POST",body:JSON.stringify({name:controllerName.value})});controllerId.value=d.controller_id;sessionStorage.setItem("fgpanel_controller_id",d.controller_id);controllerResult.textContent="Controller ID:\n"+d.controller_id+"\n\nController Key (shown once):\n"+d.controller_key+"\n\n"+d.note;controllerResult.classList.remove("hidden")}catch(e){toast(e.message,true)}
}
async function registerDevice(){
 try{const d=await api("/api/v1/devices",{method:"POST",body:JSON.stringify({controller_id:controllerId.value.trim(),mac:deviceMac.value.trim(),name:deviceName.value.trim(),room:deviceRoom.value.trim(),firmware:deviceFirmware.value.trim()})});toast("Device registered · "+d.mac);await refreshAll()}catch(e){toast(e.message,true)}
}
async function openShares(mac){activeMac=mac;shareDevice.textContent=mac;inviteResult.classList.add("hidden");shareDialog.showModal();await loadShares()}
function closeShares(){shareDialog.close()}
async function loadShares(){
 try{const d=await api("/api/v1/devices/"+activeMac+"/shares");sharesList.innerHTML=(d.shares||[]).map(s=>{
  const a=new Set(s.allowed_outlets||[]),owner=s.role==="owner",view=s.role==="view";
  const checks=[1,2,3,4].map(n=>'<label><input type="checkbox" data-user="'+esc(s.user_id)+'" value="'+n+'" '+(a.has(n)?"checked":"")+' '+(owner||view?"disabled":"")+'> '+tr("outlet")+' '+n+'</label>').join("");
  return '<div class="share"><div class="deviceHead"><div><strong>'+esc(s.email)+'</strong><div class="muted">'+esc(roleLabel(s.role))+'</div></div></div><div class="checks">'+checks+'</div>'+(owner?'<div class="muted">1–4</div>':view?'<div class="muted">View only</div>':'<button class="btn primary" onclick="saveOutlets(\''+esc(s.user_id)+'\')">'+tr("save")+'</button>')+'</div>'
 }).join("")}catch(e){sharesList.innerHTML='<div class="notice bad">'+esc(e.message)+'</div>'}
}
async function saveOutlets(uid){
 const outlets=[...document.querySelectorAll('input[data-user="'+CSS.escape(uid)+'"]:checked')].map(x=>Number(x.value));
 try{await api("/api/v1/devices/"+activeMac+"/shares/"+uid+"/outlets",{method:"PUT",body:JSON.stringify({outlets})});toast("Saved · "+outlets.join(","));await loadShares();await refreshAll()}catch(e){toast(e.message,true)}
}
async function createInvite(){
 try{const d=await api("/api/v1/devices/"+activeMac+"/shares/invites",{method:"POST",body:JSON.stringify({role:inviteRole.value,expires_hours:Number(inviteHours.value||72)})});inviteResult.textContent="Share code:\n"+d.code+"\n\nRole: "+d.role+"\nExpires: "+d.expires_at;inviteResult.classList.remove("hidden")}catch(e){toast(e.message,true)}
}
controllerId.value=sessionStorage.getItem("fgpanel_controller_id")||"";
applyLang();if(token){showDashboard();refreshAll()}else showAuth();
</script>
</body>
</html>"""


@router.get("/", response_class=RedirectResponse)
def root() -> RedirectResponse:
    return RedirectResponse(url="/panel", status_code=307)


@router.get("/panel", response_class=HTMLResponse)
@router.get("/panel/", response_class=HTMLResponse)
def panel() -> HTMLResponse:
    return HTMLResponse(
        PANEL_HTML,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'self'"
            ),
        },
    )
