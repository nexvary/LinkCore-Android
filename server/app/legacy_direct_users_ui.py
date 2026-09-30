"""Small owner management widget; no client registration or billing UI."""
USERS_WIDGET = r'''
<section id="fg-direct-users" style="margin:20px;padding:18px;border:1px solid #71828f;border-radius:12px;background:#101820;color:#eff5f8;font:16px Tahoma,Arial,sans-serif">
 <h2 id="fgdu-title"></h2><p id="fgdu-help"></p>
 <form id="fgdu-register"><label id="fgdu-mac-label" for="fgdu-mac"></label> <input id="fgdu-mac" placeholder="AABBCCDDEEFF" maxlength="12" pattern="[0-9A-Fa-f]{12}" required dir="ltr"> <button id="fgdu-register-button"></button></form>
 <form id="fgdu-create" style="margin:16px 0"><input id="fgdu-name" autocomplete="off" placeholder="username" pattern="[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}" minlength="3" maxlength="64" required dir="ltr"> <input id="fgdu-display" maxlength="120"> <button id="fgdu-create-button"></button></form>
 <pre id="fgdu-secret" style="white-space:pre-wrap;overflow-wrap:anywhere" dir="ltr"></pre><button type="button" id="fgdu-clear-secret"></button>
 <div style="margin:16px 0"><select id="fgdu-user" aria-label="User"></select> <select id="fgdu-device" aria-label="Device MAC" dir="ltr"></select> <select id="fgdu-role"></select></div>
 <div id="fgdu-outlets" style="display:flex;flex-wrap:wrap;gap:16px"></div>
 <div><button type="button" id="fgdu-save"></button> <button type="button" id="fgdu-revoke"></button> <button type="button" id="fgdu-disable"></button> <button type="button" id="fgdu-reset"></button></div>
 <p id="fgdu-status" role="status" aria-live="polite"></p>
</section>
<style>
#fg-direct-users input,#fg-direct-users select,#fg-direct-users button{font:inherit;padding:10px;margin:5px;max-width:95%;border-radius:7px;border:1px solid #8296a6;background:#223848;color:white;min-height:44px}
#fg-direct-users button{cursor:pointer}#fg-direct-users button:disabled{opacity:.5;cursor:default}
#fg-direct-users input[type=checkbox]{min-height:20px;width:20px;height:20px;vertical-align:middle}
</style>
<script>
(()=>{
const root=document.getElementById('fg-direct-users');if(!root)return;
const $=id=>root.querySelector('#fgdu-'+id),t=(ar,en)=>document.documentElement.dir==='rtl'||document.documentElement.lang.startsWith('ar')?ar:en;
let users=[],busy=false,selectAfter=null;
function text(id,ar,en){$(id).textContent=t(ar,en)}
text('title','مستخدمو ومشتركات Direct VPS','Direct VPS users and devices');
text('help','سجّل MAC أولًا، ثم أنشئ المستخدم وحدّد مخارجه. أرسل له بيانات حسابه فقط، وليس دخول المالك. لإضافة المشترك فعليًا اضبط Controller IP على 104.207.95.47 بعد التسجيل.','Register a MAC, create a user, then assign outlets. Share only their account credentials. Provision the device Controller IP to 104.207.95.47 after registration.');
text('mac-label','MAC جديد','New MAC');text('register-button','تسجيل المشترك','Register device');text('create-button','إنشاء مستخدم','Create user');
$('display').placeholder=t('اسم المستخدم الظاهر','Display name');
text('clear-secret','إخفاء بيانات الدخول','Hide login credentials');text('save','حفظ الصلاحيات','Save permissions');text('revoke','سحب الوصول للمشترك','Revoke device access');text('reset','تغيير كلمة المرور وإلغاء الجلسات','Reset password and sessions');
for(const [value,ar,en] of [['view','مشاهدة فقط','View only'],['control','تحكم حسب المخارج المختارة','Control selected outlets']]){const o=document.createElement('option');o.value=value;o.textContent=t(ar,en);$('role').append(o)}
for(let n=1;n<=4;n++){const box=document.createElement('div');const title=document.createElement('strong');title.textContent=t('مخرج ','Outlet ')+n;box.append(title);
 for(const [kind,ar,en] of [['v','مشاهدة','View'],['c','تحكم','Control']]){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.id='fgdu-'+kind+n;input.checked=kind==='v';label.append(input,document.createTextNode(t(ar,en)));box.append(label);input.addEventListener('change',()=>{if(kind==='c'&&input.checked)$('v'+n).checked=true;if(kind==='v'&&!input.checked)$('c'+n).checked=false})}$('outlets').append(box)}
async function api(path,method='GET',body){const r=await fetch('/panel/api/direct/'+path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});let j={};try{j=await r.json()}catch(_){}if(!r.ok)throw Error(typeof j.detail==='string'?j.detail:'HTTP '+r.status);return j}
function current(){return users.find(u=>u.id===$('user').value)}
function chosen(){const u=current(),g=u?.grants.find(g=>g.mac===$('device').value);for(let n=1;n<=4;n++){$('v'+n).checked=!!((g?g.view_mask:15)&(1<<(n-1)));$('c'+n).checked=!!((g?g.control_mask:0)&(1<<(n-1)))}$('role').value=g?.control_mask?'control':'view';$('disable').textContent=current()?.active?t('تعطيل الحساب وإلغاء الجلسات','Disable account and sessions'):t('تفعيل الحساب','Enable account')}
async function refresh(){const old=selectAfter||$('user').value,mac=$('device').value;selectAfter=null;const [u,d]=await Promise.all([api('users'),api('devices')]);users=u.users||[];$('user').replaceChildren();for(const user of users){const o=document.createElement('option');o.value=user.id;o.textContent=user.username+' · '+user.display_name+' · '+(user.active?t('فعال','Active'):t('معطل','Disabled'));$('user').append(o)}if(users.some(u=>u.id===old))$('user').value=old;$('device').replaceChildren();for(const dev of d.devices||[]){const o=document.createElement('option');o.value=dev.mac;o.textContent=dev.mac;$('device').append(o)}if([...$('device').options].some(o=>o.value===mac))$('device').value=mac;chosen()}
function secret(j){$('secret').textContent=t('احفظ هذه البيانات الآن؛ لن تظهر كلمة المرور مرة أخرى.','Save these credentials now; the password will not be displayed again.')+'\nHTTPS: https://link.fgmachines.org\nUsername: '+j.username+'\nPassword: '+j.password}
async function run(action){if(busy)return;busy=true;root.querySelectorAll('button').forEach(b=>b.disabled=true);text('status','جارٍ التنفيذ…','Working…');try{await action();await refresh();text('status','تم حفظ التغيير','Change saved')}catch(e){$('status').textContent=e.message}finally{busy=false;root.querySelectorAll('button').forEach(b=>b.disabled=false)}}
$('register').addEventListener('submit',e=>{e.preventDefault();run(async()=>{await api('registrations','POST',{mac:$('mac').value.trim().toUpperCase()});$('mac').value=''})});
$('create').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const j=await api('users','POST',{username:$('name').value.trim(),display_name:$('display').value.trim()});secret(j);selectAfter=j.id;$('name').value='';$('display').value=''})});
$('user').onchange=chosen;$('device').onchange=chosen;$('role').onchange=()=>{for(let n=1;n<=4;n++)$('c'+n).checked=$('role').value==='control'&&$('v'+n).checked};
$('save').onclick=()=>run(async()=>{if(!current()||!$('device').value)throw Error(t('اختر مستخدمًا ومشتركًا','Select a user and device'));let view=0,control=0;for(let n=1;n<=4;n++){if($('v'+n).checked)view|=1<<(n-1);if($('c'+n).checked)control|=1<<(n-1)}await api('users/'+encodeURIComponent(current().id)+'/devices/'+$('device').value,'PUT',{view_mask:view,control_mask:control})});
$('revoke').onclick=()=>run(async()=>{if(!current()||!$('device').value)throw Error(t('اختر مستخدمًا ومشتركًا','Select a user and device'));await api('users/'+current().id+'/devices/'+$('device').value,'DELETE')});
$('disable').onclick=()=>run(async()=>{if(!current())throw Error(t('اختر مستخدمًا','Select a user'));await api('users/'+current().id,'PATCH',{active:!current().active})});
$('reset').onclick=()=>run(async()=>{if(!current())throw Error(t('اختر مستخدمًا','Select a user'));secret(await api('users/'+current().id+'/reset-password','POST'))});
$('clear-secret').onclick=()=>{$('secret').textContent=''};
refresh().catch(e=>{$('status').textContent=e.message});
})();
</script>
'''
