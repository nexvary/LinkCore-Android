"""Self-contained card appended to the existing protected 0.5 owner panel."""
WIDGET = r'''
<section id="fg-direct-vps" style="margin:20px;padding:18px;border:1px solid #71828f;border-radius:12px;background:#101820;color:#eff5f8;font:16px Tahoma,Arial,sans-serif">
 <h2 id="fgdv-title">DIRECT VPS · TCP 10086</h2>
 <p id="fgdv-hint"></p><div id="fgdv-devices"></div><p id="fgdv-message" role="status"></p>
</section>
<style>
#fg-direct-vps .fgdv-card{padding:14px;margin:12px 0;border:1px solid #576c7e;border-radius:10px}
#fg-direct-vps .fgdv-outlets{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
#fg-direct-vps .fgdv-outlet{padding:12px;border-radius:8px;border:1px solid #65717d;background:#1c252e}
#fg-direct-vps .fgdv-on{border-color:#43d092;color:#66e7b2}
#fg-direct-vps .fgdv-off{border-color:#965565;color:#ee99aa}
#fg-direct-vps .fgdv-pending{border-color:#f0b35e;color:#f0b35e}
#fg-direct-vps .fgdv-offline{border-color:#677481;color:#abb5bf}
#fg-direct-vps button{font:inherit;padding:8px 16px;margin:8px 4px;border-radius:7px;border:1px solid #8296a6;background:#223848;color:#fff;cursor:pointer}
#fg-direct-vps button:disabled{opacity:.55;cursor:default}
#fg-direct-vps button.fgdv-toggle{min-width:140px;min-height:50px;font-size:18px;font-weight:700;border-width:2px;transition:background .15s,border-color .15s}
#fg-direct-vps button.fgdv-toggle-on{background:#147a47;border-color:#52e7a0;box-shadow:0 0 12px #32c57d30}
#fg-direct-vps button.fgdv-toggle-off{background:#a5123d;border-color:#f05a80;box-shadow:0 0 12px #d81e5730}
#fg-direct-vps button.fgdv-toggle-pending{background:#835500;border-color:#f0b35e;opacity:1}
#fg-direct-vps button.fgdv-toggle-offline{background:#39434d;border-color:#7b8997}
#fg-direct-vps button.fgdv-toggle:focus-visible{outline:3px solid #dbeeff;outline-offset:3px}
#fg-direct-vps small{display:block;margin:5px 0;color:#c4cdd4;overflow-wrap:anywhere}
</style>
<script>
(()=>{
const root=document.getElementById('fg-direct-vps');if(!root)return;
const output=root.querySelector('#fgdv-devices'),message=root.querySelector('#fgdv-message');
const pending=new Set();let devices=[],refreshing=false;
const ar=()=>document.documentElement.dir==='rtl'||document.documentElement.lang.startsWith('ar');
const t=(a,e)=>ar()?a:e;
const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){
 root.dir=ar()?'rtl':'ltr';
 root.querySelector('#fgdv-hint').textContent=t('تجربة المالك: اتصال مباشر بالخادم. أوضاع Android وLAN وZeroTier متاحة كما هي.','Owner experiment: direct server connection. Android, LAN and ZeroTier remain available.');
 output.innerHTML=devices.length?devices.map(d=>{
  const allowed=new Set(d.allowed_outlets||[]),outlets=d.outlets||[];
  const cards=[1,2,3,4].map(n=>{
   const o=outlets.find(x=>x.channel===n)||{};
   const busy=pending.has(d.mac+':'+n)||(d.pending_outlets||[]).includes(n);
   const label=!d.connected?t('غير متصل','Offline'):busy?t('قيد التنفيذ','Pending'):(o.relay||t('غير معروف','Unknown')).toUpperCase();
   const known=o.relay==='on'||o.relay==='off';
   const css=!d.connected?'offline':busy?'pending':!known?'offline':o.relay;
   const disabled=!d.connected||!d.control_enabled||busy||!allowed.has(n)||!known;
   const next=o.relay==='on'?'off':'on';
   const action=t('مخرج '+n+'، اضغط '+(next==='on'?'للتشغيل':'للإطفاء'),'Outlet '+n+', turn '+next);
   const toggle='<button type="button" class="fgdv-toggle fgdv-toggle-'+css+'" data-mac="'+esc(d.mac)+'" data-outlet="'+n+'" data-state="'+next+'" aria-label="'+esc(action)+'" '+(known?'aria-pressed="'+(o.relay==='on')+'" ':'')+(disabled?'disabled':'')+'><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle"><path d="M12 2v10M6.3 5.8a9 9 0 1 0 11.4 0"/></svg> '+esc(label)+'</button>';
   return '<div class="fgdv-outlet fgdv-'+css+'"><strong>'+t('مخرج ','Outlet ')+n+' · '+esc(label)+'</strong><small>'+esc(o.power_w)+' W · '+esc(o.energy_wh)+' Wh · '+esc(o.temperature_c)+' °C</small><small>'+t('حماية حمل / حرارة: ','Overload / overheat: ')+esc(o.overload)+' / '+esc(o.overheat)+' · '+t('حدث: ','Event: ')+esc(o.event_code)+'</small>'+toggle+'</div>';
  }).join('');
  return '<div class="fgdv-card"><strong>DIRECT VPS · TCP 10086 · '+esc(d.mac)+' · '+(d.connected?t('متصل','Online'):t('غير متصل','Offline'))+'</strong><small>'+esc(d.model)+' · '+esc(d.firmware)+' · '+esc(d.peer)+'</small><small>'+t('وقت الاتصال: ','Connected: ')+esc(d.connected_at?new Date(d.connected_at*1000).toLocaleString():'—')+' · '+t('آخر ظهور: ','Last seen: ')+esc(d.last_seen?new Date(d.last_seen*1000).toLocaleString():'—')+'</small><div class="fgdv-outlets">'+cards+'</div></div>';
 }).join(''):esc(t('لا توجد أجهزة Direct VPS مسجلة.','No registered Direct VPS devices.'));
}
async function api(path,options={}){
 const response=await fetch(path,{credentials:'same-origin',...options});let data={};try{data=await response.json()}catch(_){}
 if(!response.ok)throw Error(data.detail||('HTTP '+response.status));return data;
}
async function refresh(){if(refreshing)return;refreshing=true;try{const result=await api('/panel/api/direct/devices');devices=result.devices||[];render()}catch(e){message.textContent=e.message}finally{refreshing=false}}
root.addEventListener('click',async e=>{
 const button=e.target.closest('button[data-mac]');if(!button||button.disabled)return;
 const {mac,outlet,state}=button.dataset,key=mac+':'+outlet;if(pending.has(key))return;
 pending.add(key);render();message.textContent=t('بانتظار تأكيد المشترك…','Waiting for device confirmation…');
 try{const result=await api('/panel/api/direct/devices/'+encodeURIComponent(mac)+'/outlets/'+outlet+'?state='+state,{method:'POST'});message.textContent=result.status+' · '+(result.detail||'')}
 catch(error){message.textContent=error.message}finally{pending.delete(key);await refresh()}
});
new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['dir','lang']});
render();refresh();setInterval(refresh,5000);
})();
</script>
'''

# Shared visual shell for the installed 0.5 panel, preserving its original DOM/events.
PANEL_LAYOUT = r'''
<style>
:root{--fg-bg:#0b121b;--fg-card:#121e2b;--fg-line:#506277;--fg-text:#e8f0f8;--fg-muted:#a9bacb;--fg-blue:#76c5ff}
body.fg-panel{margin:0!important;background:var(--fg-bg)!important;color:var(--fg-text)!important;font:16px/1.6 Tahoma,Arial,sans-serif!important}
.fg-panel *{box-sizing:border-box}.fg-panel [hidden]{display:none!important}
#fg-panel-header{position:sticky;top:0;z-index:20;background:#0d1723f5;border-bottom:1px solid var(--fg-line);backdrop-filter:blur(12px);padding:16px max(20px,calc((100vw - 1440px)/2))}
#fg-panel-header .fg-panel-brand{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
#fg-panel-header h1{font-size:24px;margin:0;color:#edf7ff}#fg-panel-header p{margin:2px 0;color:var(--fg-muted);font-size:14px}
.fg-panel-tag{border:1px solid #6e9cbc;border-radius:8px;padding:4px 12px;color:var(--fg-blue);font-size:13px;white-space:nowrap}
#fg-panel-nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
#fg-panel-nav button{font:inherit;font-weight:700;padding:10px 18px;min-height:46px;border:1px solid var(--fg-line);border-radius:9px;background:#192737;color:var(--fg-text);cursor:pointer}
#fg-panel-nav button[aria-pressed=true]{background:#234b6a;border-color:var(--fg-blue);color:#fff;box-shadow:0 0 14px #76c5ff18}
#fg-panel-main{max-width:1440px;margin:auto;padding:22px 20px 40px;min-width:0}
#fg-panel-main>section{margin:0!important;padding:22px!important;border:1px solid var(--fg-line)!important;border-radius:14px!important;background:var(--fg-card)!important;color:var(--fg-text)!important;font:inherit!important;min-width:0}
#fg-panel-main h2{font-size:22px;margin:0 0 10px;color:#e8f4ff}#fg-panel-main p{color:var(--fg-muted)}
#fg-panel-main input:not([type=checkbox]),#fg-panel-main select{font:inherit;font-size:16px;padding:10px 12px;margin:0;min-height:46px;max-width:100%;border-radius:8px;border:1px solid #607890;background:#0d1723;color:var(--fg-text);min-width:0}
#fg-panel-main button{min-height:44px;border-radius:8px;font-family:inherit;font-size:15px}#fg-panel-main button:focus-visible,#fg-panel-nav button:focus-visible,#fg-panel-main input:focus-visible,#fg-panel-main select:focus-visible{outline:3px solid var(--fg-blue);outline-offset:3px}
#fg-direct-users .fgdu-block{padding:18px;background:#0f1926;border:1px solid #3d5268;border-radius:12px;margin:16px 0}
#fg-direct-users .fgdu-block h3{margin:0 0 12px;font-size:18px;color:#d9edff}
#fg-direct-users form,#fg-direct-users .fgdu-selection{display:flex;align-items:center;flex-wrap:wrap;gap:10px}
#fg-direct-users form input{flex:1 1 210px}#fg-direct-users button{margin:0;padding:10px 16px;background:#234b6a;border:1px solid #648ba8;color:#fff}
#fg-direct-users .fgdu-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
#fg-direct-users #fgdu-revoke,#fg-direct-users #fgdu-disable{background:#522535;border-color:#9d526b}
#fg-direct-users #fgdu-reset{background:#554319;border-color:#b69a58}
#fg-direct-users #fgdu-outlets{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px!important;margin-top:16px}
#fgdu-outlets>div{display:flex;flex-direction:column;gap:8px;background:#182738;padding:14px;border:1px solid #4b627a;border-radius:9px}
#fgdu-outlets label{display:flex;align-items:center;gap:8px}#fgdu-outlets input[type=checkbox]{margin:0;accent-color:#76c5ff}
#fgdu-secret:empty,#fgdu-secret:empty+button{display:none}#fgdu-secret:not(:empty){padding:16px;border:1px solid #b69a58;background:#302819;border-radius:9px;color:#fff;font-size:16px}
#fg-direct-vps .fgdv-card{background:#0f1926;border-color:#4b627a;padding:18px;margin-top:18px}
#fg-direct-vps .fgdv-outlets{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:14px}
#fg-direct-vps .fgdv-outlet{padding:16px;background:#182738}#fg-direct-vps small{font-size:14px;line-height:1.7}
#fg-direct-vps .fgdv-toggle{width:100%;margin:12px 0 0}
#fg-panel-legacy>*,#fg-panel-audit>*{max-width:100%}
#fg-panel-legacy section,#fg-panel-legacy .card,#fg-panel-audit section,#fg-panel-audit .card{background:#0f1926!important;color:var(--fg-text)!important;border:1px solid #4b627a!important;border-radius:12px!important;padding:16px!important;margin-bottom:16px!important}
#fg-panel-main table{width:100%;border-collapse:collapse;font-size:14px}#fg-panel-main th,#fg-panel-main td{padding:12px 10px;text-align:start;border-bottom:1px solid #34475b;overflow-wrap:anywhere}#fg-panel-main th{color:#d7e9f9;background:#192b3e}
#fg-panel-audit{overflow:auto;max-height:calc(100vh - 185px)}#fg-panel-audit th{position:sticky;top:0;z-index:1}
#fg-panel-legacy{overflow-x:auto}#fg-panel-main [role=status]{padding:10px 0;overflow-wrap:anywhere}
/* Black / neon identity, including legacy hover rules and inherited labels. */
body.fg-panel{--fg-bg:#020403;--fg-card:#080d0b;--fg-text:#79ff9d;--fg-muted:#63df87;--fg-line:#70857a;--fg-blue:#82ffa5;font-size:17px!important}
#fg-panel-header{background:#030805f5}#fg-panel-header h1,#fg-panel-header p,#fg-panel-main h2,#fg-panel-main h3,#fg-panel-main p,#fg-panel-main small,#fg-panel-main label,#fg-panel-main strong,#fg-panel-main summary{color:var(--fg-text)!important}
#fg-panel-main h2,#fg-panel-header h1{text-shadow:0 0 16px #41ff7730}#fg-panel-main h3{font-size:19px}
#fg-panel-main>section{box-shadow:0 12px 32px #0008,inset 0 1px 0 #c0e0cc12}
#fg-panel-nav button,#fg-direct-users button{background:#0b1811;color:#79ff9d;border-color:#768e80;transition:background .16s,border-color .16s,box-shadow .16s,transform .16s}
#fg-panel-nav button[aria-pressed=true]{background:#102d1b;color:#8affad;border-color:#79ff9d;box-shadow:0 0 14px #42ff6c22}
#fg-panel-main input:not([type=checkbox]),#fg-panel-main select,#fg-panel-main textarea{background:#020705;color:#79ff9d;border-color:#758d7f;font-size:17px;min-height:48px;caret-color:#79ff9d}
#fg-panel-main input::placeholder,#fg-panel-main textarea::placeholder{color:#58b772;opacity:1}#fg-panel-main option{color:#79ff9d;background:#06100a}
#fg-direct-users{display:grid;grid-template-columns:1fr 1fr;gap:16px}#fg-direct-users>h2,#fg-direct-users>p,#fg-direct-users>.fgdu-block:nth-of-type(3){grid-column:1/-1}
#fg-direct-users .fgdu-block{margin:0;padding:20px;background:#050a07;border:1px solid #73887c;border-radius:14px;box-shadow:inset 0 1px 0 #dcffe918;min-width:0}
#fg-direct-users .fgdu-selection select,#fgdu-user{min-width:min(100%,260px)}
#fg-direct-users #fgdu-outlets{gap:16px!important}#fgdu-outlets>div{padding:18px;background:linear-gradient(145deg,#0c1c12,#040906);border:1px solid #7b9586;border-radius:12px;box-shadow:0 5px 15px #0005}
#fgdu-outlets strong{font-size:19px;margin-bottom:8px}#fgdu-outlets label{display:flex!important;flex-direction:row!important;justify-content:flex-start!important;align-items:center!important;width:auto!important;margin:0!important;padding:6px 0!important;gap:12px!important;text-align:start!important;cursor:pointer;font-size:17px}
#fgdu-outlets input[type=checkbox],#fg-direct-users .fgdu-device-list input[type=checkbox]{width:22px!important;height:22px!important;min-height:22px!important;margin:0!important;float:none!important;flex:0 0 22px;accent-color:#54ff83;cursor:pointer}
#fg-direct-users .fgdu-device-list label{display:flex!important;justify-content:flex-start!important;gap:12px!important;background:#06100a;border:1px solid #718b7a;font-size:16px;min-height:54px;cursor:pointer}
#fgdu-assigned span{color:#79ff9d;background:#0c2414;border-color:#6fa180}
#fg-direct-users #fgdu-revoke,#fg-direct-users #fgdu-disable{background:#22080f;border-color:#a45c71;color:#79ff9d}#fg-direct-users #fgdu-reset{background:#231c07;border-color:#a9904d;color:#79ff9d}
#fg-direct-vps .fgdv-card{background:#030805;border-color:#82998b;border-radius:14px}#fg-direct-vps .fgdv-outlet{background:linear-gradient(145deg,#0c1911,#040906);padding:20px;border-radius:12px;box-shadow:0 5px 15px #0005}
#fg-direct-vps button.fgdv-toggle-on{background:#083c20;color:#8affaf;border-color:#52ff88}#fg-direct-vps button.fgdv-toggle-off{background:#520b26;color:#ff9fbd;border-color:#f34c81}#fg-direct-vps button.fgdv-toggle-pending{background:#483200;color:#ffe6a1}#fg-direct-vps button.fgdv-toggle-offline{background:#1b211d;color:#bac9c0}
#fg-panel-main button:disabled{opacity:.48;cursor:not-allowed;box-shadow:none}#fg-panel-main table th{background:#0b1b11;color:#79ff9d}#fg-panel-main table td{color:#79ff9d;border-color:#334a3b}
#fg-panel-legacy section,#fg-panel-legacy .card,#fg-panel-audit section,#fg-panel-audit .card{background:#030805!important;color:#79ff9d!important;border-color:#758d7f!important}
@media(hover:hover){#fg-panel-nav button:hover,#fg-panel-main button:not(:disabled):hover{background:#183c24;color:#a0ffbb;border-color:#88ffaa;box-shadow:0 0 18px #47ff7738;transform:translateY(-2px)}#fg-direct-vps button.fgdv-toggle-off:not(:disabled):hover{background:#751135;color:#ffd0df;border-color:#ff7aa4}#fg-direct-vps button.fgdv-toggle-on:not(:disabled):hover{background:#105832;color:#b3ffc9}#fg-direct-users .fgdu-block:hover,#fg-direct-vps .fgdv-outlet:hover,#fgdu-outlets>div:hover{border-color:#99c9ab;box-shadow:0 0 20px #52ff7d14}#fg-direct-users .fgdu-device-list label:hover{background:#112c1a;border-color:#79ff9d}}
#fg-panel-main button:not(:disabled):active,#fg-panel-nav button:active{transform:translateY(0);box-shadow:inset 0 2px 8px #0008}#fg-direct-users .fgdu-block:focus-within{border-color:#79ff9d}#fgdu-outlets>div:has(input:checked){border-color:#86b898}
@media(max-width:850px){#fg-direct-users{grid-template-columns:1fr}#fg-direct-users>.fgdu-block{grid-column:1/-1}}
/* Keep form captions inside their own fields despite the original panel CSS. */
#fg-direct-users #fgdu-create{display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:14px!important;width:100%!important;align-items:stretch!important}
#fg-direct-users .fgdu-field{display:grid;gap:7px;min-width:0}#fg-direct-users .fgdu-field>label,#fg-direct-users #fgdu-macs-label{all:unset!important;display:block!important;position:static!important;float:none!important;width:100%!important;min-width:0!important;margin:0!important;padding:0!important;color:#79ff9d!important;font:inherit!important}
#fg-direct-users .fgdu-field input{width:100%!important;min-width:0!important;margin:0!important}#fg-direct-users .fgdu-password-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;min-width:0}
#fg-direct-users #fgdu-password-help{display:block;font-size:14px;line-height:1.7;overflow-wrap:anywhere}#fg-direct-users #fgdu-create-button{width:100%;margin-top:2px}
#fg-direct-users #fgdu-outlets>div{display:grid!important;grid-template-columns:minmax(0,1fr)!important;align-content:start!important;gap:8px!important;min-width:0!important;min-height:166px!important;padding:20px!important;overflow:hidden;isolation:isolate}
#fg-direct-users #fgdu-outlets strong{display:block;position:static!important;float:none!important;width:auto!important;margin:0 0 4px!important;padding:0!important;line-height:1.5!important}
#fg-direct-users #fgdu-outlets input[type=checkbox]{position:static!important;float:none!important;transform:none!important;inset:auto!important;appearance:auto!important;align-self:center!important;justify-self:start!important}
#fg-direct-users #fgdu-devices label{all:unset!important;display:flex!important;flex-wrap:wrap!important;align-items:center!important;justify-content:flex-start!important;gap:10px!important;position:static!important;float:none!important;width:auto!important;min-width:0!important;min-height:54px!important;padding:12px!important;margin:0!important;border:1px solid #718b7a!important;border-radius:9px!important;background:#06100a!important;color:#79ff9d!important;cursor:pointer!important;direction:inherit!important}
#fg-direct-users #fgdu-devices input{position:static!important;float:none!important;transform:none!important;inset:auto!important;appearance:auto!important;width:22px!important;height:22px!important;min-height:22px!important;flex:0 0 22px!important;margin:0!important}
#fg-direct-users #fgdu-devices bdi{position:static!important;float:none!important;font:15px monospace!important;direction:ltr!important;unicode-bidi:isolate!important;overflow-wrap:anywhere!important;min-width:0!important}
#fg-direct-users #fgdu-device{width:100%;max-width:100%;min-width:0;flex:1 1 280px}#fg-direct-users #fgdu-device-help{font-size:15px;margin-top:12px}
@media(prefers-reduced-motion:reduce){#fg-panel-nav button,#fg-panel-main button{transition:none!important;transform:none!important}}
@media(max-width:850px){#fg-direct-vps .fgdv-outlets,#fg-direct-users #fgdu-outlets{grid-template-columns:repeat(2,minmax(0,1fr))}#fg-panel-header{position:relative}#fg-panel-main>section{padding:16px!important}}
@media(max-width:480px){#fg-panel-header{padding:14px 12px}#fg-panel-main{padding:14px 10px}#fg-panel-nav{display:grid;grid-template-columns:1fr 1fr}#fg-panel-nav button{padding:10px 8px;font-size:14px}#fg-direct-vps .fgdv-outlets,#fg-direct-users #fgdu-outlets{grid-template-columns:1fr}#fg-panel-main h2{font-size:20px}#fg-panel-audit{max-height:none}}
</style>
<script>
(()=>{
function mount(){
 if(document.getElementById('fg-panel-header'))return;
 const direct=document.getElementById('fg-direct-vps'),users=document.getElementById('fg-direct-users');if(!direct||!users)return;
 const originals=[...document.body.children].filter(el=>el!==direct&&el!==users&&!['SCRIPT','STYLE','LINK'].includes(el.tagName));
 const header=document.createElement('header');header.id='fg-panel-header';
 header.innerHTML='<div class="fg-panel-brand"><div><h1>FG Link</h1><p id="fg-panel-subtitle"></p></div><span class="fg-panel-tag">DIRECT VPS · ANDROID / LAN</span></div><nav id="fg-panel-nav" aria-label="Panel"></nav>';
 const main=document.createElement('main');main.id='fg-panel-main';
 const legacy=document.createElement('section');legacy.id='fg-panel-legacy';
 const audit=document.createElement('section');audit.id='fg-panel-audit';
 for(const el of originals)legacy.append(el);
 // Move only a self-contained audit card. Leave unrecognized legacy structures intact.
 for(const heading of legacy.querySelectorAll('h2,h3')){
  if(!/سجل النشاط|activity\s*log|audit\s*log/i.test(heading.textContent))continue;
  const card=heading.closest('section,.card');if(card&&card!==legacy){audit.append(card);break}
  let parent=heading.parentElement;while(parent&&parent!==legacy&&!parent.querySelector('table'))parent=parent.parentElement;if(parent&&parent!==legacy&&parent.querySelectorAll('h2,h3').length===1){audit.append(parent);break}
 }
 if(!audit.children.length){const hint=document.createElement('p');hint.id='fg-panel-audit-hint';audit.append(hint)}
 main.append(direct,users,legacy,audit);document.body.prepend(header);header.after(main);document.body.classList.add('fg-panel');
 const views=[['devices',direct,'المشتركات والتحكم','Devices & control'],['users',users,'المستخدمون والصلاحيات','Users & permissions'],['local',legacy,'Android / LAN','Android / LAN'],['audit',audit,'سجل النشاط','Activity log']];
 let active='devices';const nav=header.querySelector('nav');
 function show(key){active=key;for(const [id,panel] of views){panel.hidden=id!==key;nav.querySelector('[data-view="'+id+'"]').setAttribute('aria-pressed',String(id===key))}}
 for(const [id,panel,ar,en] of views){const button=document.createElement('button');button.type='button';button.dataset.view=id;button.setAttribute('aria-controls',panel.id);button.onclick=()=>show(id);nav.append(button)}
 function translate(){const ar=document.documentElement.dir==='rtl'||document.documentElement.lang.startsWith('ar');header.querySelector('#fg-panel-subtitle').textContent=ar?'لوحة إدارة المشتركات والحسابات':'Device and account administration';nav.setAttribute('aria-label',ar?'أقسام لوحة الإدارة':'Administration sections');for(const [id,panel,a,e] of views)nav.querySelector('[data-view="'+id+'"]').textContent=ar?a:e;const hint=document.getElementById('fg-panel-audit-hint');if(hint)hint.textContent=ar?'سجل النشاط متاح داخل قسم Android / LAN في هذه النسخة من الخادم.':'The activity log is available in Android / LAN on this server version.'}
 new MutationObserver(translate).observe(document.documentElement,{attributes:true,attributeFilter:['dir','lang']});translate();show(active);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
</script>
'''
