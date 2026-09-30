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
#fg-direct-vps button:disabled{opacity:.4;cursor:default}
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
   const css=!d.connected?'offline':busy?'pending':o.relay==='on'?'on':'off';
   const disabled=!d.connected||!d.control_enabled||busy||!allowed.has(n);
   return '<div class="fgdv-outlet fgdv-'+css+'"><strong>'+t('مخرج ','Outlet ')+n+' · '+esc(label)+'</strong><small>'+esc(o.power_w)+' W · '+esc(o.energy_wh)+' Wh · '+esc(o.temperature_c)+' °C</small><small>'+t('حماية حمل / حرارة: ','Overload / overheat: ')+esc(o.overload)+' / '+esc(o.overheat)+' · '+t('حدث: ','Event: ')+esc(o.event_code)+'</small>'+['on','off'].map(s=>'<button type="button" data-mac="'+esc(d.mac)+'" data-outlet="'+n+'" data-state="'+s+'" '+(disabled?'disabled':'')+'>'+s.toUpperCase()+'</button>').join('')+'</div>';
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
