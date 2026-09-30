from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)

PANEL_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#0a0f14">
  <title>FG Machines Link — Operations Console</title>
  <style>
    :root{
      --bg:#0a0f14;--bg2:#0d1319;--panel:#111820;--panel2:#151d26;--panel3:#0f151c;
      --line:#24313c;--line2:#31404c;--text:#f2f5f7;--muted:#84919d;--soft:#b6c0c8;
      --accent:#4aa3df;--accent2:#2f7faf;--green:#4fc98a;--red:#df6671;--amber:#d6a354;
      --shadow:0 16px 40px rgba(0,0,0,.28);--radius:12px;
    }
    .badge.pending{color:var(--amber)} .badge.offstate{color:var(--red)} button:disabled{opacity:.4;cursor:default}
    *{box-sizing:border-box}
    html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Tahoma,Arial,sans-serif}
    body{background:linear-gradient(180deg,#0a0f14 0,#0b1117 48%,#091016 100%)}
    button,input,select{font:inherit}
    button{cursor:pointer}
    .app{min-height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr)}
    .sidebar{
      position:sticky;top:0;height:100vh;padding:20px 16px;border-inline-end:1px solid var(--line);
      background:#0b1015;display:flex;flex-direction:column;gap:18px
    }
    .brand{display:flex;align-items:center;gap:12px;padding:4px 6px 18px;border-bottom:1px solid var(--line)}
    .brandMark{width:42px;height:42px;border:1px solid #35596f;background:#0f202b;display:grid;place-items:center;font-weight:800;letter-spacing:.5px;color:#79c6f2}
    .brandText strong{display:block;font-size:15px;letter-spacing:.2px}.brandText span{display:block;color:var(--muted);font-size:11px;margin-top:3px}
    .nav{display:grid;gap:5px}
    .nav button{display:flex;align-items:center;gap:10px;width:100%;border:0;background:transparent;color:#9ba9b5;padding:10px 11px;text-align:start;border-radius:8px}
    .nav button:hover{background:#111a22;color:var(--text)}
    .nav button.active{background:#14212b;color:#dbeef9;border:1px solid #294557}
    .navIcon{width:18px;height:18px;display:grid;place-items:center;color:#6eb6df;font-size:13px}
    .sideMeta{margin-top:auto;padding:12px;border-top:1px solid var(--line);display:grid;gap:9px}
    .sideMetaRow{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:11px}
    .statusDot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-inline-end:6px;background:var(--green);box-shadow:0 0 0 3px rgba(79,201,138,.1)}
    .sideActions{display:grid;grid-template-columns:1fr 1fr;gap:7px}
    .main{min-width:0}
    .topbar{
      height:68px;padding:0 24px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;
      background:rgba(13,19,25,.94);backdrop-filter:blur(10px);position:sticky;top:0;z-index:8
    }
    .topTitle{display:flex;align-items:center;gap:13px}.topTitle h1{font-size:18px;margin:0;font-weight:650}.topTitle span{font-size:12px;color:var(--muted)}
    .topActions{display:flex;align-items:center;gap:8px}
    .btn{border:1px solid var(--line2);background:#101820;color:var(--text);border-radius:8px;padding:8px 11px;min-height:36px}
    .btn:hover{border-color:#4a6576;background:#14202a}.btn.primary{background:#153448;border-color:#346c8f;color:#dff3ff}
    .btn.good{background:#123326;border-color:#2c6c50;color:#dff7e9}.btn.danger{background:#34191e;border-color:#76404a;color:#ffdce0}
    .btn.ghost{background:transparent}.btn.small{padding:6px 9px;min-height:30px;font-size:12px}.btn:disabled{opacity:.32;cursor:not-allowed}
    .content{padding:22px 24px 34px;max-width:1640px;margin:auto}
    .pageIntro{display:flex;align-items:end;justify-content:space-between;gap:18px;margin-bottom:18px}
    .pageIntro h2{font-size:22px;margin:0 0 5px;font-weight:650}.pageIntro p{margin:0;color:var(--muted);font-size:13px}
    .kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}
    .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 15px;min-height:86px}
    .kpiHead{display:flex;justify-content:space-between;gap:12px;align-items:center;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.45px}
    .kpiValue{font-size:25px;font-weight:700;margin-top:11px}.kpiSub{font-size:11px;color:var(--muted);margin-top:4px}.ok{color:var(--green)}.bad{color:var(--red)}.amber{color:var(--amber)}
    .panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
    .panelHead{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:14px 16px;border-bottom:1px solid var(--line);background:#111922}
    .panelHead h3{font-size:14px;margin:0;font-weight:650}.panelHead p{margin:3px 0 0;color:var(--muted);font-size:11px}
    .panelBody{padding:15px}
    .layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(320px,.8fr);gap:14px;align-items:start}
    .tableWrap{overflow:auto}
    table{width:100%;border-collapse:collapse;min-width:920px}
    th,td{padding:11px 12px;border-bottom:1px solid #1f2b34;text-align:start;vertical-align:middle}
    th{font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:#73818d;font-weight:650;background:#0f161d}
    td{font-size:12px;color:#d9e0e5}.deviceName{font-weight:650;color:#f3f6f8}.subline{display:block;color:var(--muted);font-size:10px;margin-top:3px}
    .mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;color:#8d9ba6}
    .badge{display:inline-flex;align-items:center;gap:6px;border:1px solid #34434f;border-radius:999px;padding:4px 8px;font-size:10px;color:#b8c3cb;background:#0e151b}
    .badge.online{border-color:#285f46;color:#9fe0be;background:#10281e}.badge.offline{border-color:#603941;color:#e9a4ab;background:#29161a}
    .role{border-color:#36556a;color:#b9d9ec}.outletSet{display:flex;gap:4px;flex-wrap:wrap}
    .port{width:27px;height:25px;display:grid;place-items:center;border-radius:5px;border:1px solid #394854;background:#10171d;color:#707d87;font-size:10px;font-weight:700}
    .port.allowed{border-color:#37664f;color:#9edabb;background:#10231b}.port.denied{opacity:.34}
    .powerActions{display:flex;gap:5px;flex-wrap:wrap}.powerBtn{min-width:34px;height:28px;border-radius:6px;border:1px solid #32414d;background:#10171d;color:#9ca9b2;font-size:10px;font-weight:700}
    .powerBtn.on{border-color:#2e6c4f;color:#a3e0c0}.powerBtn.off{border-color:#6a3841;color:#e5a5ab}.powerBtn:disabled{opacity:.25}
    .formGrid{display:grid;gap:10px}.field{display:grid;gap:5px}.field label{font-size:10px;color:#7e8b96;text-transform:uppercase;letter-spacing:.4px}
    .field input,.field select{width:100%;background:#0b1117;color:var(--text);border:1px solid #2c3944;border-radius:7px;padding:9px 10px;outline:none}
    .field input:focus,.field select:focus{border-color:#4a88ac;box-shadow:0 0 0 3px rgba(74,136,172,.12)}
    .row2{display:grid;grid-template-columns:1fr 1fr;gap:9px}
    .divider{height:1px;background:var(--line);margin:13px 0}
    .note{padding:10px 11px;border:1px solid var(--line);border-radius:8px;background:#0d141a;color:var(--muted);font-size:11px;line-height:1.65;white-space:pre-wrap}
    .secret{border-color:#6f5931;color:#ead29b;background:#241f14}
    .empty{padding:34px;text-align:center;color:var(--muted)}
    .section{scroll-margin-top:88px}
    dialog{width:min(820px,94vw);max-height:86vh;padding:0;border:1px solid var(--line2);border-radius:12px;background:#0e151c;color:var(--text);box-shadow:0 30px 90px rgba(0,0,0,.6)}
    dialog::backdrop{background:rgba(0,0,0,.72)}
    .modalHead{position:sticky;top:0;z-index:3;padding:13px 15px;border-bottom:1px solid var(--line);background:#111922;display:flex;align-items:center;justify-content:space-between}
    .modalHead strong{font-size:14px}.modalBody{padding:15px}
    .shareRow{border:1px solid var(--line);border-radius:9px;padding:12px;margin-top:9px;background:#0c1319}
    .shareTop{display:flex;justify-content:space-between;gap:12px}.checks{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}
    .checks label{display:flex;align-items:center;gap:5px;border:1px solid #33424e;border-radius:6px;padding:6px 8px;font-size:11px;color:#aeb9c2}
    .toast{position:fixed;inset-inline-start:20px;bottom:20px;z-index:40;max-width:460px;padding:11px 13px;border:1px solid #3c6d8b;border-radius:8px;background:#111922;box-shadow:0 18px 45px rgba(0,0,0,.45);font-size:12px}
    .hidden{display:none!important}
    @media(max-width:1100px){.app{grid-template-columns:78px minmax(0,1fr)}.brandText,.navLabel,.sideMetaRow span:last-child{display:none}.sidebar{padding:16px 10px}.brand{justify-content:center}.nav button{justify-content:center}.sideActions{grid-template-columns:1fr}.layout{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
    @media(max-width:720px){.app{display:block}.sidebar{position:static;height:auto;border-inline-end:0;border-bottom:1px solid var(--line);padding:10px;display:flex;flex-direction:row;align-items:center}.brand{border:0;padding:0}.brandText{display:block}.nav{display:flex;overflow:auto}.nav button{min-width:max-content}.sideMeta{display:none}.topbar{padding:0 12px}.topTitle span{display:none}.content{padding:14px 10px 24px}.kpis{grid-template-columns:1fr 1fr}.layout{grid-template-columns:1fr}.row2{grid-template-columns:1fr}.pageIntro{align-items:start;flex-direction:column}.topActions .btn:not(#langBtn):not(#logoutBtn){display:none}}
  </style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="brandMark">FG</div>
      <div class="brandText"><strong>FG Machines Link</strong><span>Cloud Operations</span></div>
    </div>

    <nav class="nav">
      <button class="active" onclick="goSection('overview',this)"><span class="navIcon">◫</span><span class="navLabel" id="navOverview">نظرة عامة</span></button>
      <button onclick="goSection('devices',this)"><span class="navIcon">▦</span><span class="navLabel" id="navDevices">الأجهزة</span></button>
      <button onclick="goSection('infrastructure',this)"><span class="navIcon">⌘</span><span class="navLabel" id="navInfra">البنية التحتية</span></button>
      <button onclick="location.href='/docs'"><span class="navIcon">↗</span><span class="navLabel">API Docs</span></button>
    </nav>

    <div class="sideMeta">
      <div class="sideMetaRow"><span><span class="statusDot"></span><span id="sideStatus">Cloud API</span></span><span>0.3.0</span></div>
      <div class="sideActions">
        <button class="btn ghost small" id="langBtn" onclick="toggleLang()">English</button>
        <button class="btn danger small hidden" id="logoutBtn" onclick="logout()">خروج</button>
      </div>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="topTitle"><div><h1 id="consoleTitle">Operations Console</h1><span id="consoleSub">إدارة أجهزة FG Link والمشتركين وصلاحيات المخارج</span></div></div>
      <div class="topActions">
        <button class="btn small" onclick="refreshAll()" id="refreshTop">تحديث البيانات</button>
        <button class="btn small" onclick="location.href='/docs'">API</button>
      </div>
    </header>

    <section id="authView" class="content">
      <div class="panel" style="max-width:520px;margin:55px auto">
        <div class="panelHead"><div><h3 id="authTitle">تسجيل الدخول</h3><p id="authText">FG Link Cloud Operations</p></div><span class="badge">SECURE SESSION</span></div>
        <div class="panelBody">
          <div class="formGrid">
            <div class="field"><label id="emailLabel">البريد الإلكتروني</label><input id="email" type="email" autocomplete="username"></div>
            <div class="field"><label id="passwordLabel">كلمة المرور</label><input id="password" type="password" autocomplete="current-password"></div>
            <div style="display:flex;gap:8px">
              <button class="btn primary" id="loginBtn" onclick="login()">دخول</button>
              <button class="btn" id="registerBtn" onclick="registerAccount()">إنشاء حساب</button>
            </div>
            <div id="authMsg" class="note hidden"></div>
          </div>
        </div>
      </div>
    </section>

    <div id="dashboard" class="hidden">
      <div class="content">
        <section id="overview" class="section">
          <div class="pageIntro">
            <div><h2 id="overviewTitle">الحالة التشغيلية</h2><p id="overviewSub">الخادم وسيط نقل فقط؛ أوامر الكهرباء لا تُنفّذ دون توقيع الهاتف المرتبط.</p></div>
            <span class="badge online"><span class="statusDot"></span><span id="liveBadge">SYSTEM OPERATIONAL</span></span>
          </div>

          <div class="kpis">
            <div class="kpi"><div class="kpiHead"><span id="kpiServer">Cloud API</span><span>01</span></div><div class="kpiValue ok" id="serverState">ONLINE</div><div class="kpiSub" id="serverSub">HTTPS gateway available</div></div>
            <div class="kpi"><div class="kpiHead"><span id="kpiDevices">Registered Devices</span><span>02</span></div><div class="kpiValue" id="deviceCount">0</div><div class="kpiSub" id="deviceSub">MTTL nodes</div></div>
            <div class="kpi"><div class="kpiHead"><span id="kpiOnline">Online Now</span><span>03</span></div><div class="kpiValue ok" id="onlineCount">0</div><div class="kpiSub" id="onlineSub">Heartbeat within threshold</div></div>
            <div class="kpi"><div class="kpiHead"><span id="kpiVersion">Platform Version</span><span>04</span></div><div class="kpiValue amber">0.3.0</div><div class="kpiSub">FG Link Cloud</div></div>
          </div>
        </section>

        <div class="layout">
          <section id="devices" class="panel section">
            <div class="panelHead">
              <div><h3 id="devicesTitle">Device Operations</h3><p id="devicesHint">التحكم متاح فقط للمخارج المخصصة لهذا الحساب.</p></div>
              <button class="btn small" onclick="refreshAll()" id="refreshBtn">Refresh</button>
            </div>
            <div class="tableWrap">
              <table>
                <thead><tr><th id="thDevice">الجهاز</th><th id="thStatus">الحالة</th><th id="thRole">الصلاحية</th><th id="thPorts">المخارج</th><th id="thControl">التحكم</th><th id="thManage">الإدارة</th></tr></thead>
                <tbody id="deviceRows"></tbody>
              </table>
              <div id="emptyDevices" class="empty hidden">لا توجد أجهزة مسجلة.</div>
            </div>
          </section>

          <section id="infrastructure" class="panel section">
            <div class="panelHead"><div><h3 id="infraTitle">Infrastructure Provisioning</h3><p id="infraSub">إنشاء Controller وربط أجهزة MTTL بالخادم.</p></div></div>
            <div class="panelBody">
              <div class="formGrid">
                <div class="field"><label id="controllerNameLabel">Controller Name</label><input id="controllerName" value="FG Link Android Controller"></div>
                <button class="btn good" id="createControllerBtn" onclick="createController()">Create Controller</button>
                <div id="controllerResult" class="note secret hidden"></div>
                <div class="divider"></div>
                <div class="field"><label>Controller ID</label><input id="controllerId"></div>
                <div class="field"><label>MAC</label><input id="deviceMac" placeholder="AABBCCDDEEFF"></div>
                <div class="row2">
                  <div class="field"><label id="deviceNameLabel">Device Name</label><input id="deviceName" placeholder="MTTL-W01"></div>
                  <div class="field"><label id="roomLabel">Room / Location</label><input id="deviceRoom"></div>
                </div>
                <div class="field"><label>Firmware</label><input id="deviceFirmware"></div>
                <button class="btn primary" id="registerDeviceBtn" onclick="registerDevice()">Register Device</button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </main>
</div>

<dialog id="shareDialog">
  <div class="modalHead"><strong id="shareTitle">Subscriber Access Control</strong><button class="btn small" onclick="closeShares()">×</button></div>
  <div class="modalBody">
    <div id="shareDevice" class="note"></div>
    <div class="row2">
      <div class="field"><label id="inviteRoleLabel">Invite Role</label><select id="inviteRole"><option value="view">View</option><option value="control" selected>Control</option><option value="admin">Admin</option></select></div>
      <div class="field"><label id="inviteHoursLabel">Invite Lifetime</label><input id="inviteHours" type="number" value="72" min="1" max="720"></div>
    </div>
    <div style="margin-top:10px"><button class="btn good" id="createInviteBtn" onclick="createInvite()">Create Share Code</button></div>
    <div id="inviteResult" class="note secret hidden" style="margin-top:10px"></div>
    <div id="sharesList"></div>
  </div>
</dialog>

<div id="toast" class="toast hidden"></div>

<script>
const T={
 ar:{
  pending:"قيد التنفيذ",protection:"الحماية",connectedAt:"وقت الاتصال",lastSeen:"آخر ظهور",dir:"rtl",langBtn:"English",logout:"خروج",consoleTitle:"Operations Console",consoleSub:"إدارة أجهزة FG Link والمشتركين وصلاحيات المخارج",
  navOverview:"نظرة عامة",navDevices:"الأجهزة",navInfra:"البنية التحتية",authTitle:"تسجيل الدخول",authText:"جلسة إدارية مشفرة عبر FG Link Cloud",
  email:"البريد الإلكتروني",password:"كلمة المرور",login:"دخول",register:"إنشاء حساب",overviewTitle:"الحالة التشغيلية",overviewSub:"وضع Android يتطلب توقيع الهاتف؛ وضع Direct VPS التجريبي يتحكم عبر جلسة TCP مباشرة.",
  liveBadge:"النظام يعمل",kpiServer:"الخادم",kpiDevices:"الأجهزة المسجلة",kpiOnline:"متصل الآن",kpiVersion:"إصدار المنصة",
  serverSub:"بوابة HTTPS متاحة",deviceSub:"أجهزة MTTL",onlineSub:"جلسة Direct TCP أو Heartbeat Android",devicesTitle:"تشغيل الأجهزة",devicesHint:"التحكم متاح فقط للمخارج المخصصة لهذا الحساب.",
  refresh:"تحديث البيانات",thDevice:"الجهاز",thStatus:"الحالة",thRole:"الصلاحية",thPorts:"المخارج",thControl:"التحكم",thManage:"الإدارة",
  noDevices:"لا توجد أجهزة مسجلة.",connected:"متصل",offline:"غير متصل",owner:"مالك",control:"تحكم",admin:"مدير",view:"مشاهدة",
  manage:"المشتركون",infraTitle:"تجهيز البنية التحتية",infraSub:"إنشاء Controller وربط أجهزة MTTL بالخادم.",controllerName:"اسم Controller",
  createController:"إنشاء Controller",deviceName:"اسم الجهاز",room:"الغرفة / الموقع",registerDevice:"تسجيل الجهاز",shareTitle:"إدارة صلاحيات المشتركين",
  inviteRole:"صلاحية الدعوة",inviteHours:"مدة الدعوة بالساعات",createInvite:"إنشاء كود مشاركة",save:"حفظ المخارج",outlet:"مخرج",on:"ON",off:"OFF"
 },
 en:{
  pending:"Pending",protection:"Protection",connectedAt:"Connected",lastSeen:"Last seen",dir:"ltr",langBtn:"العربية",logout:"Sign out",consoleTitle:"Operations Console",consoleSub:"FG Link device, subscriber and outlet authorization management",
  navOverview:"Overview",navDevices:"Devices",navInfra:"Infrastructure",authTitle:"Sign in",authText:"Administrative session through FG Link Cloud",
  email:"Email",password:"Password",login:"Sign in",register:"Create account",overviewTitle:"Operational Status",overviewSub:"Android commands require the bound phone signature; experimental Direct VPS uses the live TCP session.",
  liveBadge:"SYSTEM OPERATIONAL",kpiServer:"Cloud API",kpiDevices:"Registered Devices",kpiOnline:"Online Now",kpiVersion:"Platform Version",
  serverSub:"HTTPS gateway available",deviceSub:"MTTL nodes",onlineSub:"Direct TCP session or Android heartbeat",devicesTitle:"Device Operations",devicesHint:"Controls appear only for outlets assigned to this account.",
  refresh:"Refresh Data",thDevice:"Device",thStatus:"Status",thRole:"Role",thPorts:"Outlets",thControl:"Control",thManage:"Management",
  noDevices:"No devices registered.",connected:"Online",offline:"Offline",owner:"Owner",control:"Control",admin:"Admin",view:"View",
  manage:"Subscribers",infraTitle:"Infrastructure Provisioning",infraSub:"Create a controller and attach MTTL devices to the server.",controllerName:"Controller Name",
  createController:"Create Controller",deviceName:"Device Name",room:"Room / Location",registerDevice:"Register Device",shareTitle:"Subscriber Access Control",
  inviteRole:"Invite Role",inviteHours:"Invite Lifetime (hours)",createInvite:"Create Share Code",save:"Save Outlets",outlet:"Outlet",on:"ON",off:"OFF"
 }
};
let lang=localStorage.getItem("fgpanel_lang")||"ar";
let token=sessionStorage.getItem("fgpanel_token")||"";
let devices=[],activeMac="";

function tr(k){return (T[lang]&&T[lang][k])||k}
function esc(v){return String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]))}
function applyLang(){
 document.documentElement.lang=lang;document.documentElement.dir=T[lang].dir;
 const map={langBtn:"langBtn",logoutBtn:"logout",consoleTitle:"consoleTitle",consoleSub:"consoleSub",navOverview:"navOverview",navDevices:"navDevices",navInfra:"navInfra",
 authTitle:"authTitle",authText:"authText",emailLabel:"email",passwordLabel:"password",loginBtn:"login",registerBtn:"register",overviewTitle:"overviewTitle",overviewSub:"overviewSub",
 liveBadge:"liveBadge",kpiServer:"kpiServer",kpiDevices:"kpiDevices",kpiOnline:"kpiOnline",kpiVersion:"kpiVersion",serverSub:"serverSub",deviceSub:"deviceSub",onlineSub:"onlineSub",
 devicesTitle:"devicesTitle",devicesHint:"devicesHint",refreshTop:"refresh",refreshBtn:"refresh",thDevice:"thDevice",thStatus:"thStatus",thRole:"thRole",thPorts:"thPorts",
 thControl:"thControl",thManage:"thManage",emptyDevices:"noDevices",infraTitle:"infraTitle",infraSub:"infraSub",controllerNameLabel:"controllerName",createControllerBtn:"createController",
 deviceNameLabel:"deviceName",roomLabel:"room",registerDeviceBtn:"registerDevice",shareTitle:"shareTitle",inviteRoleLabel:"inviteRole",inviteHoursLabel:"inviteHours",createInviteBtn:"createInvite"};
 for(const [id,key] of Object.entries(map)){const e=document.getElementById(id);if(e)e.textContent=tr(key)}
 renderDevices();
}
function toggleLang(){lang=lang==="ar"?"en":"ar";localStorage.setItem("fgpanel_lang",lang);applyLang()}
function goSection(id,btn){document.getElementById(id)?.scrollIntoView({behavior:"smooth"});document.querySelectorAll(".nav button").forEach(x=>x.classList.remove("active"));btn.classList.add("active")}
function toast(msg,bad=false){const e=document.getElementById("toast");e.textContent=msg;e.style.borderColor=bad?"var(--red)":"#3c6d8b";e.classList.remove("hidden");setTimeout(()=>e.classList.add("hidden"),3800)}
async function api(path,opts={}){
 const headers={"Content-Type":"application/json",...(opts.headers||{})};if(token)headers.Authorization="Bearer "+token;
 const r=await fetch(path,{...opts,headers});let data={};try{data=await r.json()}catch(_){}
 if(!r.ok){if(r.status===401&&token){logout();}throw new Error(data.detail||("HTTP "+r.status))}
 return data
}
function showDashboard(){authView.classList.add("hidden");dashboard.classList.remove("hidden");logoutBtn.classList.remove("hidden")}
function showAuth(){authView.classList.remove("hidden");dashboard.classList.add("hidden");logoutBtn.classList.add("hidden")}
async function login(){try{const d=await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email:email.value,password:password.value})});token=d.access_token;sessionStorage.setItem("fgpanel_token",token);showDashboard();await refreshAll()}catch(e){authError(e.message)}}
async function registerAccount(){try{const d=await api("/api/v1/auth/register",{method:"POST",body:JSON.stringify({email:email.value,password:password.value})});token=d.access_token;sessionStorage.setItem("fgpanel_token",token);showDashboard();await refreshAll()}catch(e){authError(e.message)}}
function authError(m){authMsg.textContent=m;authMsg.classList.remove("hidden")}
function logout(){token="";sessionStorage.removeItem("fgpanel_token");showAuth()}
async function refreshAll(){
 try{
  const [h,d,ctls]=await Promise.all([api("/healthz"),api("/api/v1/devices"),api("/api/v1/controllers")]);devices=d.devices||[];
  serverState.textContent=h.ok?"ONLINE":"ERROR";serverState.className="kpiValue "+(h.ok?"ok":"bad");
  deviceCount.textContent=devices.length;onlineCount.textContent=devices.filter(x=>x.connected).length;
  const cs=ctls.controllers||[];if(!controllerId.value&&cs.length){controllerId.value=cs[0].controller_id;sessionStorage.setItem("fgpanel_controller_id",controllerId.value)}
  renderDevices()
 }catch(e){toast(e.message,true)}
}
function roleLabel(r){return tr(r)||r}
function renderDevices(){
 const body=document.getElementById("deviceRows"),empty=document.getElementById("emptyDevices");if(!body)return;
 if(!devices.length){body.innerHTML="";empty.classList.remove("hidden");return}empty.classList.add("hidden");
 body.innerHTML=devices.map(d=>{
  const allowed=new Set(d.allowed_outlets||[]);
  const ports=[1,2,3,4].map(n=>'<span class="port '+(allowed.has(n)?"allowed":"denied")+'">'+n+'</span>').join("");
  const direct=d.transport==="direct-vps";
  const telemetry=(d.outlets||[]).map(o=>'<span class="subline">'+tr("outlet")+' '+o.channel+' · '+esc(o.relay)+' · '+esc(o.power_w??"—")+' W · '+esc(o.energy_wh??"—")+' Wh · '+esc(o.temperature_c??"—")+' °C · '+esc(o.event_code??"")+'</span>').join("");
  const controls=direct?[1,2,3,4].map(n=>{
    const o=(d.outlets||[]).find(x=>x.channel===n)||{};
    const pending=(d.pending_outlets||[]).includes(n)||pendingCommands.has(d.mac+":"+n);
    const disabled=!d.connected||!d.control_enabled||!allowed.has(n)||pending;
    return '<div><span class="badge '+(!d.connected?'offline':pending?'pending':o.relay==='on'?'online':'offstate')+'">'+tr("outlet")+' '+n+' · '+(!d.connected?tr("offline"):pending?tr('pending'):esc(o.relay||'—'))+'</span> '+['on','off'].map(state=>'<button class="btn small" '+(disabled?'disabled':'')+' onclick="setOutlet(\''+d.mac+'\','+n+',\''+state+'\')">'+state.toUpperCase()+'</button>').join(' ')+'</div>';
  }).join("")+telemetry:'<span class="badge role">ANDROID KEY SIGNATURE</span>';
  const canAdmin=d.role==="owner"||d.role==="admin";
  return '<tr><td><span class="deviceName">'+esc(d.name||"MTTL-W01")+'</span><span class="subline">'+esc(d.room||"—")+'</span><span class="mono">'+esc(d.mac)+'</span><span class="badge">'+(direct?'DIRECT VPS · TCP 10086':'ANDROID / LAN')+'</span>'+(direct?'<span class="subline">'+esc(d.model||'')+' · '+esc(d.firmware||'')+' · '+esc(d.peer||'')+'</span><span class="subline">Connected: '+esc(d.connected_at?new Date(d.connected_at*1000).toLocaleString():'—')+' · '+tr('lastSeen')+': '+esc(d.last_seen?new Date(d.last_seen).toLocaleString():'—')+'</span>':'')+'</td>'+
    '<td><span class="badge '+(d.connected?"online":"offline")+'">'+(d.connected?tr("connected"):tr("offline"))+'</span></td>'+
    '<td><span class="badge role">'+esc(roleLabel(d.role))+'</span></td>'+
    '<td><div class="outletSet">'+ports+'</div></td>'+
    '<td><div class="powerActions">'+controls+'</div></td>'+
    '<td>'+(canAdmin?'<button class="btn small" onclick="openShares(\''+d.mac+'\')">'+tr("manage")+'</button>':'—')+'</td></tr>'
 }).join("")
}
const pendingCommands=new Set();
async function setOutlet(mac,outlet,state){
 const key=mac+":"+outlet;if(pendingCommands.has(key))return;
 pendingCommands.add(key);renderDevices();
 try{const d=await api("/api/v1/devices/"+mac+"/direct-outlets/"+outlet+"?state="+state,{method:"POST"});toast(d.status+" · "+(d.detail||""),d.status!=="confirmed")}
 catch(e){toast(e.message,true)}finally{pendingCommands.delete(key);await refreshAll()}
}
async function createController(){
 try{const d=await api("/api/v1/controllers",{method:"POST",body:JSON.stringify({name:controllerName.value})});controllerId.value=d.controller_id;sessionStorage.setItem("fgpanel_controller_id",d.controller_id);controllerResult.textContent="Controller ID:\n"+d.controller_id+"\n\nController Key (shown once):\n"+d.controller_key+"\n\n"+d.note;controllerResult.classList.remove("hidden")}catch(e){toast(e.message,true)}
}
async function registerDevice(){try{const d=await api("/api/v1/devices",{method:"POST",body:JSON.stringify({controller_id:controllerId.value.trim(),mac:deviceMac.value.trim(),name:deviceName.value.trim(),room:deviceRoom.value.trim(),firmware:deviceFirmware.value.trim()})});toast("Device registered · "+d.mac);await refreshAll()}catch(e){toast(e.message,true)}}
async function openShares(mac){activeMac=mac;shareDevice.textContent=mac;inviteResult.classList.add("hidden");shareDialog.showModal();await loadShares()}
function closeShares(){shareDialog.close()}
async function loadShares(){
 try{const d=await api("/api/v1/devices/"+activeMac+"/shares");sharesList.innerHTML=(d.shares||[]).map(s=>{
  const a=new Set(s.allowed_outlets||[]),owner=s.role==="owner",view=s.role==="view";
  const checks=[1,2,3,4].map(n=>'<label><input type="checkbox" data-user="'+esc(s.user_id)+'" value="'+n+'" '+(a.has(n)?"checked":"")+' '+(owner||view?"disabled":"")+'> '+tr("outlet")+' '+n+'</label>').join("");
  return '<div class="shareRow"><div class="shareTop"><div><strong>'+esc(s.email)+'</strong><span class="subline">'+esc(roleLabel(s.role))+'</span></div><span class="badge role">'+esc(roleLabel(s.role))+'</span></div><div class="checks">'+checks+'</div>'+(owner?'<div class="note">1–4</div>':view?'<div class="note">View only</div>':'<button class="btn primary small" onclick="saveOutlets(\''+esc(s.user_id)+'\')">'+tr("save")+'</button>')+'</div>'
 }).join("")}catch(e){sharesList.innerHTML='<div class="note bad">'+esc(e.message)+'</div>'}
}
async function saveOutlets(uid){const outlets=[...document.querySelectorAll('input[data-user="'+CSS.escape(uid)+'"]:checked')].map(x=>Number(x.value));try{await api("/api/v1/devices/"+activeMac+"/shares/"+uid+"/outlets",{method:"PUT",body:JSON.stringify({outlets})});toast("Saved · "+outlets.join(","));await loadShares();await refreshAll()}catch(e){toast(e.message,true)}}
async function createInvite(){try{const d=await api("/api/v1/devices/"+activeMac+"/shares/invites",{method:"POST",body:JSON.stringify({role:inviteRole.value,expires_hours:Number(inviteHours.value||72)})});inviteResult.textContent="Share code:\n"+d.code+"\n\nRole: "+d.role+"\nExpires: "+d.expires_at;inviteResult.classList.remove("hidden")}catch(e){toast(e.message,true)}}
controllerId.value=sessionStorage.getItem("fgpanel_controller_id")||"";
setInterval(()=>{if(token&&!pendingCommands.size)refreshAll()},5000);
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
