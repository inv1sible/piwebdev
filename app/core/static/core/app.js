const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
function esc(s){return String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function md(s){
  let src=String(s??'').replace(/\r\n/g,'\n').replace(/([^\n])\s+-\s+(?=(\*\*|`|[A-Z0-9]))/g,'$1\n- ');
  const blocks=[];
  src=src.replace(/\[([^\]]+)\]\(([^)]+)\)/g,(_,text,href)=>{
    const k=`@@BLK${blocks.length}@@`;
    blocks.push(`<a href="${href.replace(/"/g,'&quot;')}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`);
    return k;
  });
  let x=esc(src).replace(/```([\s\S]*?)```/g,(_,c)=>{
    const k=`@@BLK${blocks.length}@@`;
    const code=c.replace(/^\n|\n$/g,'');
    blocks.push(`<pre><button class="copy-btn" onclick="navigator.clipboard.writeText(this.nextElementSibling.textContent)">copy</button><code>${code}</code></pre>`);
    return k;
  });
  x=x.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/(^|\s)_([^_]+)_/g,'$1<em>$2</em>');
  const out=[]; let list=null, quote=[];
  function close(){if(list){out.push(list==='ol'?'</ol>':'</ul>');list=null} if(quote.length){out.push(`<blockquote>${quote.join('')}</blockquote>`);quote=[]}}
  for(const line of x.split('\n')){let m; if(line.trim()===''){close(); continue}
    if((m=line.match(/^(#{1,4})\s+(.+)/))){close(); out.push(`<h${m[1].length}>${m[2]}</h${m[1].length}>`)}
    else if((m=line.match(/^[-*]\s+(.+)/))){if(list!=='ul'){close();list='ul';out.push('<ul>')} out.push(`<li>${m[1]}</li>`)}
    else if((m=line.match(/^\d+[.)]\s+(.+)/))){if(list!=='ol'){close();list='ol';out.push('<ol>')} out.push(`<li>${m[1]}</li>`)}
    else if((m=line.match(/^>\s?(.+)/))){if(list){close()} quote.push(`<p>${m[1]}</p>`)}
    else {close(); out.push(`<p>${line}</p>`)}
  }
  close(); return out.join('').replace(/@@BLK(\d+)@@/g,(_,i)=>blocks[i]);
}
function renderDiff(text){
  if(!text)return '';
  return text.split('\n').map(line=>{
    let cls='';
    if(/^(\+\+\+|---|diff |index )/.test(line)) cls='diff-meta';
    else if(line.startsWith('@@')) cls='diff-hunk';
    else if(line.startsWith('+')) cls='diff-add';
    else if(line.startsWith('-')) cls='diff-rem';
    return cls?`<span class="${cls}">${esc(line)}</span>`:esc(line);
  }).join('\n');
}
function csrf(){return document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||''}

document.addEventListener('click',e=>{if(e.target.matches('[data-toggle-menu]')) $('#mainNav')?.classList.toggle('open')})

const shell=$('.project-shell');
if(shell){
  const sessionId=shell.dataset.sessionId, projectId=shell.dataset.projectId;
  const messagesEl=()=>$('#messages');
  let userScrolled=false, _scrollLock=false;
  function scrollChatEnd(smooth=false){const m=messagesEl(); if(!m||userScrolled)return; _scrollLock=true; requestAnimationFrame(()=>{m.scrollTo({top:m.scrollHeight,behavior:smooth?'smooth':'auto'}); setTimeout(()=>{_scrollLock=false},smooth?600:100)})}
  function scrollToEl(el,smooth=false){if(!el||userScrolled)return; _scrollLock=true; requestAnimationFrame(()=>{el.scrollIntoView({behavior:smooth?'smooth':'auto',block:'end'}); setTimeout(()=>{_scrollLock=false},100)})}
  function setViewportHeight(){
    const vv=window.visualViewport;
    const h=vv?vv.height:window.innerHeight;
    document.documentElement.style.setProperty('--vvh',h+'px');
    scrollChatEnd();
  }
  setViewportHeight();
  window.visualViewport?.addEventListener('resize',setViewportHeight);
  window.visualViewport?.addEventListener('scroll',setViewportHeight);
  window.addEventListener('resize',setViewportHeight);

  function applyLayout(){shell.classList.remove('hide-chat'); const l=localStorage.piwebdevLeft||'300', r=localStorage.piwebdevRight||'390'; const left=shell.classList.contains('hide-left')?'0px':l+'px'; const lh=shell.classList.contains('hide-left')?'0px':'8px'; const rh=shell.classList.contains('hide-right')?'0px':'8px'; const right=shell.classList.contains('hide-right')?'0px':r+'px'; shell.style.gridTemplateColumns=`${left} ${lh} minmax(320px,1fr) ${rh} ${right}`; const la=document.querySelector('[data-collapse="left"]'), ra=document.querySelector('[data-collapse="right"]'); if(la)la.textContent=shell.classList.contains('hide-left')?'→':'←'; if(ra)ra.textContent=shell.classList.contains('hide-right')?'←':'→'}
  if(localStorage.piwebdevHideLeft==='1') shell.classList.add('hide-left');
  if(localStorage.piwebdevHideRight==='1') shell.classList.add('hide-right');
  applyLayout();
  $$('[data-collapse]').forEach(b=>b.onclick=()=>{
    const side=b.dataset.collapse;
    if(!['left','right'].includes(side))return;
    shell.classList.toggle('hide-'+side);
    localStorage['piwebdevHide'+side[0].toUpperCase()+side.slice(1)]=shell.classList.contains('hide-'+side)?'1':'';
    applyLayout();
  });
  $$('.resize-handle').forEach(h=>h.onpointerdown=e=>{e.preventDefault(); h.setPointerCapture(e.pointerId); const startX=e.clientX, startL=parseInt(localStorage.piwebdevLeft||'300'), startR=parseInt(localStorage.piwebdevRight||'390'); h.onpointermove=ev=>{if(h.dataset.resize==='left'){const w=startL+ev.clientX-startX; if(w<90){shell.classList.add('hide-left')}else{shell.classList.remove('hide-left'); localStorage.piwebdevLeft=Math.max(120,Math.min(560,w))}} else {const w=startR-(ev.clientX-startX); if(w<110){shell.classList.add('hide-right')}else{shell.classList.remove('hide-right'); localStorage.piwebdevRight=Math.max(180,Math.min(720,w))}} applyLayout()}; h.onpointerup=()=>h.onpointermove=null});

  const proto=location.protocol==='https:'?'wss':'ws';
  const wsUrl=`${proto}://${location.host}/ws/sessions/${sessionId}/`;
  let ws=null, wsDelay=1000;
  let assistant=null, thinking=null, activeTools=new Map(), currentTask=null;
  let piWorking=false, workStart=0, workingTimer=null, statusBase='';
  let sessionStart=0, sessionTimer=null, toolsTotal=0, currentModel='', currentProvider='', wsReconnectTimer=null;
  let wasResumed=false;

  function elapsed(){
    const s=Math.floor((Date.now()-workStart)/1000);
    return s<60?`${s}s`:`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
  }

  function setWorking(on){
    piWorking=on;
    const btn=$('#abortBtn');
    if(btn){btn.style.display=on?'':'none'; if(!on){btn.disabled=false; btn.textContent='■ Stop';}}
    if(on){
      if(!workingTimer){workStart=Date.now(); workingTimer=setInterval(()=>{const t=`${statusBase} (${elapsed()})`;const el=$('#wsStatus');if(el)el.textContent=t;const sc=$('#wsStatusCompact');if(sc)sc.textContent=t;},1000)}
    } else if(workingTimer){clearInterval(workingTimer); workingTimer=null}
  }

  function setStatus(text,working=false){
    statusBase=text;
    const disp=working&&workingTimer?`${text} (${elapsed()})`:text;
    const isReconn=text.startsWith('reconnecting');
    const s=$('#wsStatus');
    s.textContent=disp; s.classList.toggle('working',working); s.classList.toggle('reconnecting',isReconn);
    const sc=$('#wsStatusCompact');
    if(sc){sc.textContent=disp; sc.classList.toggle('working',working); sc.classList.toggle('reconnecting',isReconn);}
    setWorking(working);
  }

  function startSessionTimer(){
    if(sessionTimer)return;
    sessionStart=Date.now(); toolsTotal=0;
    sessionTimer=setInterval(updateRuntimeBar,1000);
    updateRuntimeBar();
  }
  function stopSessionTimer(){if(sessionTimer){clearInterval(sessionTimer);sessionTimer=null;}}
  function updateRuntimeBar(){
    const bar=$('#runtimeBar'); if(!bar)return;
    const chips=[];
    if(currentModel)chips.push(`<span class="rc hi">${esc(currentModel)}</span>`);
    if(currentProvider&&currentProvider!==currentModel)chips.push(`<span class="rc">${esc(currentProvider)}</span>`);
    if(toolsTotal>0)chips.push(`<span class="rc">${toolsTotal} tool${toolsTotal>1?'s':''}</span>`);
    if(sessionStart){const s=Math.floor((Date.now()-sessionStart)/1000);chips.push(`<span class="rc">${s<60?s+'s':Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}</span>`);}
    bar.innerHTML=chips.join('');
  }
  function scheduleReconnect(){
    if(wsReconnectTimer)clearTimeout(wsReconnectTimer);
    wsReconnectTimer=setTimeout(()=>{wsReconnectTimer=null;connectWs();},wsDelay);
    wsDelay=Math.min(wsDelay*2,30000);
  }

  function createTaskGroup(promptText,isAuto=false){
    const wrap=document.createElement('div');
    wrap.className='task-wrap';
    const el=document.createElement('details');
    el.className='task-group running'; el.open=true;
    const promptStyle=isAuto?'style="font-style:italic;opacity:.65"':'';
    el.innerHTML=`<summary class="task-summary"><span class="task-chevron">▾</span><span class="task-prompt" ${promptStyle}>${esc(promptText.slice(0,72))}</span><span class="task-badge working">working</span></summary><div class="task-body"></div>`;
    const resultEl=document.createElement('div');
    resultEl.className='task-result hidden';
    el.appendChild(resultEl); wrap.appendChild(el);
    $('#messages').appendChild(wrap); scrollChatEnd();
    return {el,body:el.querySelector('.task-body'),resultEl};
  }
  function finaliseTaskGroup(task,assistantEl,state='done'){
    task.el.classList.remove('running');
    const badge=task.el.querySelector('.task-badge');
    badge.className='task-badge '+state; badge.textContent=state;
    if(assistantEl){
      assistantEl.classList.add('final');
      task.resultEl.appendChild(assistantEl);
      task.resultEl.classList.remove('hidden');
    }
  }
  function finishCurrentTask(state='done'){
    if(currentTask) finaliseTaskGroup(currentTask,assistant,state);
    else if(assistant) assistant.classList.add('final');
    assistant=null; thinking=null; currentTask=null; activeTools=new Map();
  }
  function ensureTask(){if(!currentTask)currentTask=createTaskGroup('continuing…',true);}

  function add(role,content,raw=false){
    const el=document.createElement('div'); el.className='msg '+role;
    if(raw)el.dataset.raw=content;
    el.innerHTML=role==='assistant'?md(content):esc(content);
    const target=(currentTask&&role!=='user')?currentTask.body:$('#messages');
    target.appendChild(el); scrollChatEnd(); return el;
  }
  function addDetails(role,title,open=false,content=''){
    const el=document.createElement('details'); el.className='msg '+role; el.open=!!open;
    el.innerHTML=`<summary>${title}</summary><div class="details-body">${content}</div>`;
    const target=(currentTask&&role!=='user')?currentTask.body:$('#messages');
    target.appendChild(el); scrollChatEnd();
    return {el,body:el.querySelector('.details-body')};
  }
  function toast(msg,type='ok'){
    const el=document.createElement('div');
    el.className='toast '+type; el.textContent=msg;
    document.body.appendChild(el);
    requestAnimationFrame(()=>el.classList.add('show'));
    setTimeout(()=>{el.classList.remove('show'); setTimeout(()=>el.remove(),300)},3200);
  }
  function showError(msg){
    const el=document.createElement('div');
    el.className='msg tool error';
    el.textContent='Error: '+msg;
    const target=currentTask?currentTask.body:$('#messages');
    target.appendChild(el); scrollChatEnd();
  }

  function resultText(r){
    if(!r)return '';
    if(typeof r==='string')return r;
    if(Array.isArray(r.content))return r.content.map(x=>x?.text??x?.data??JSON.stringify(x,null,2)).join('\n');
    if(r.stdout||r.stderr)return [r.stdout,r.stderr].filter(Boolean).join('\n');
    return JSON.stringify(r,null,2);
  }
  function toolState(e){
    if(e.type==='tool_execution_start')return {icon:'▶',label:'running',cls:'running'};
    if(e.type==='tool_execution_update')return {icon:'…',label:'streaming',cls:'running'};
    if(e.isError)return {icon:'✗',label:'error',cls:'error'};
    return {icon:'✓',label:'done',cls:'done'};
  }
  function toolHtml(e){
    const name=e.toolName||e.name||'tool', args=e.args||{}, command=args.command||args.cmd||args.path||args.file||'';
    const st=toolState(e);
    const titleHtml=`<span class="ts-badge ${st.cls}">${esc(st.icon)}</span><span class="ts-tool">${esc(name)}</span>${command?`<code class="ts-cmd">${esc(command.slice(0,80))}</code>`:''}`;
    const parts=[`<div class="tool-meta ${st.cls}"><span>${esc(st.label)}</span><span>${esc(name)}</span></div>`];
    if(command)parts.push(`<div class="tool-command"><div class="tool-label">command</div><pre>${esc(command)}</pre></div>`);
    const argLines=Object.entries(args).filter(([k])=>!['command','cmd'].includes(k)).map(([k,v])=>`<div class="tool-row"><span>${esc(k)}</span><code>${esc(typeof v==='string'?v:JSON.stringify(v))}</code></div>`).join('');
    if(argLines)parts.push(`<div class="tool-args">${argLines}</div>`);
    const out=resultText(e.result)||resultText(e.partialResult);
    if(out)parts.push(`<div class="tool-output"><div class="tool-label">output</div><pre>${esc(out)}</pre></div>`);
    parts.push(`<details class="raw-json"><summary>raw event</summary><pre>${esc(JSON.stringify(e,null,2))}</pre></details>`);
    return {titleHtml,body:parts.join(''),state:st.cls,id:e.toolCallId||`${name}-${Date.now()}`};
  }
  function upsertToolEvent(e){
    const f=toolHtml(e); let item=activeTools.get(f.id);
    if(!item){item=addDetails('tool '+f.state,f.titleHtml,true,f.body); activeTools.set(f.id,item)}
    else {item.el.className='msg tool '+f.state; item.el.querySelector('summary').innerHTML=f.titleHtml; item.body.innerHTML=f.body}
    if(e.type==='tool_execution_end'){item.el.open=!!e.isError; activeTools.delete(f.id)}
    return item;
  }
  function renderStoredTool(raw){try{return toolHtml(JSON.parse(raw))}catch{return {titleHtml:esc('Tool output'),body:`<pre>${esc(raw)}</pre>`}}}

  function connectWs(){
    if(ws&&(ws.readyState===WebSocket.OPEN||ws.readyState===WebSocket.CONNECTING))return;
    ws=new WebSocket(wsUrl);
    ws.onopen=()=>{wsDelay=1000; setStatus('connected')};
    ws.onclose=(e)=>{
      if(piWorking){
        // Don't finalize — keep the task in running state so it can be adopted on reconnect
        assistant=null; thinking=null; currentTask=null; activeTools=new Map();
      }
      setWorking(false); stopSessionTimer();
      setStatus(`reconnecting... (${e.code})`);
      scheduleReconnect();
    };
    ws.onerror=()=>setStatus('ws error — check console');
    ws.onmessage=ev=>{
      const m=JSON.parse(ev.data);
      if(m.type==='status'){
        if(m.model)currentModel=m.model;
        if(m.provider)currentProvider=m.provider;
        const working=m.working??(m.message!=='idle'&&m.message!=='connected'&&!m.message.startsWith('reconnecting'));
        if(m.message==='pi ready')startSessionTimer();
        if(!working&&m.message==='idle'){
          try{finishCurrentTask('done');}catch(err){}
          if(wasResumed){wasResumed=false;toast('Loading full history…','ok');setTimeout(()=>location.reload(),1200);}
        }
        if(working&&(m.message.startsWith('resumed')||m.message.startsWith('catching'))){
          wasResumed=true;
          startSessionTimer();
          if(!currentTask){
            const all=$$('.task-group'), last=all[all.length-1];
            if(last){
              const badge=last.querySelector('.task-badge');
              if(badge&&!badge.classList.contains('done')){
                last.classList.add('running'); last.open=true;
                badge.className='task-badge working'; badge.textContent='working';
                const section=last.closest('.session-section'); if(section)section.open=true;
                const playBtn=last.querySelector('.play-btn'); if(playBtn)playBtn.style.display='none';
                let resultEl=last.querySelector('.task-result');
                if(!resultEl){resultEl=document.createElement('div');resultEl.className='task-result hidden';last.appendChild(resultEl);}
                currentTask={el:last,body:last.querySelector('.task-body'),resultEl};
                scrollChatEnd();
              }
            }
          }
        }
        setStatus(m.message,working);
        updateRuntimeBar();
        return;
      }
      if(m.type==='assistant_delta'){setStatus('agent working',true); ensureTask(); if(!assistant)assistant=add('assistant','',true); assistant.dataset.raw=(assistant.dataset.raw||'')+m.delta; assistant.innerHTML=md(assistant.dataset.raw); scrollChatEnd(); return}
      if(m.type==='pi'){
        const e=m.event||{}, d=e.assistantMessageEvent||{};
        if(e.type==='agent_start'||e.type==='turn_start')setStatus('agent working',true);
        if(e.type==='message_update'&&d.type==='thinking_delta'){setStatus('thinking',true); ensureTask(); if(!thinking)thinking=addDetails('analysis','Analysis / thinking',false); thinking.body.dataset.raw=(thinking.body.dataset.raw||'')+d.delta; thinking.body.innerHTML=md(thinking.body.dataset.raw); scrollToEl(thinking.el); return}
        if(e.type==='tool_execution_start'){ensureTask(); toolsTotal++; setStatus('running: '+(e.toolName||'tool'),true); upsertToolEvent(e); updateRuntimeBar();}
        if(e.type==='tool_execution_update')upsertToolEvent(e);
        if(e.type==='tool_execution_end'){setStatus('agent working',true); upsertToolEvent(e); if(['Write','Edit','NotebookEdit','MultiEdit'].includes(e.toolName))loadTree(currentPath);}
        if(e.type==='agent_end'){
          setStatus('idle'); updateRuntimeBar();
          try{finishCurrentTask('done'); loadTree(currentPath);}catch(err){}
          return;
        }
      }
      if(m.type==='checkpoint'){location.reload();return;}
      if(m.type==='toast'){toast(m.message,m.toast_type||'ok'); return;}
      if(m.type==='stderr')addDetails('tool','stderr',false,esc(m.content));
      if(m.type==='tool')addDetails('tool','tool output',false,esc(m.content));
      if(m.type==='message'){
        if(m.role==='user') currentTask=createTaskGroup(m.content);
        else add(m.role,m.content);
      }
    };
  }
  connectWs();
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible'&&(!ws||ws.readyState===WebSocket.CLOSED||ws.readyState===WebSocket.CLOSING)){
      wsDelay=1000;
      if(wsReconnectTimer){clearTimeout(wsReconnectTimer);wsReconnectTimer=null;}
      connectWs();
    }
  });
  window.addEventListener('pageshow',e=>{
    if(e.persisted&&(!ws||ws.readyState!==WebSocket.OPEN)){
      wsDelay=1000;
      if(wsReconnectTimer){clearTimeout(wsReconnectTimer);wsReconnectTimer=null;}
      connectWs();
    }
  });

  $('#abortBtn').onclick=()=>{const b=$('#abortBtn'); if(b){b.disabled=true;b.textContent='stopping…'} setStatus('stopping…',true); if(ws&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'abort'}))};

  $('#composer').onsubmit=e=>{e.preventDefault(); const ta=$('#prompt'), msg=ta.value.trim(); if(!msg)return; if(!ws||ws.readyState!==WebSocket.OPEN){setStatus('not connected — wait or reload'); return;} $$('#messages .task-group').forEach(d=>d.open=false); userScrolled=false; ws.send(JSON.stringify({type:'prompt',message:msg})); ta.value=''; ta.style.height=''; setStatus('sending…',true);};
  $('#prompt').onfocus=()=>{document.body.classList.add('keyboard-open'); setViewportHeight(); setTimeout(()=>{scrollChatEnd(); $('#composer').scrollIntoView({block:'end',behavior:'smooth'})},250)};
  $('#prompt').onblur=()=>document.body.classList.remove('keyboard-open');
  $('#prompt').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('#composer').requestSubmit()}};
  $('#prompt').oninput=function(){this.style.height='auto'; this.style.height=Math.min(this.scrollHeight,240)+'px'};

  let currentPath='', currentFile='', pressTimer=null;
  async function api(url,opt={}){const r=await fetch(url,{...opt,headers:{'X-CSRFToken':csrf(),...(opt.headers||{})}}); const j=await r.json(); if(!r.ok)throw new Error(j.error||'request failed'); return j}
  async function loadTree(path=''){
    currentPath=path;
    try{
      const j=await api(`/api/projects/${projectId}/files/?path=${encodeURIComponent(path)}`);
      $('#fileTree').innerHTML=(path?`<button class="file" data-dir="${path.split('/').slice(0,-1).join('/')}">..</button>`:'')+j.items.map(i=>`<button class="file" data-${i.is_dir?'dir':'file'}="${esc((path?path+'/':'')+i.name)}">${i.is_dir?'📁':'📄'} ${esc(i.name)}</button>`).join('');
    }catch(err){showError(err.message)}
  }
  $('#fileTree').onclick=e=>{const b=e.target.closest('button'); if(!b||b.dataset.longpress==='1'){if(b)b.dataset.longpress='';return} if(b.dataset.dir!==undefined)loadTree(b.dataset.dir); if(b.dataset.file!==undefined)openFile(b.dataset.file)};
  $('#fileTree').onpointerdown=e=>{const b=e.target.closest('button.file'); if(!b)return; pressTimer=setTimeout(()=>{b.dataset.longpress='1'; showFileMenu(b.dataset.file??b.dataset.dir, b.dataset.file===undefined)},650)};
  $('#fileTree').onpointerup=$('#fileTree').onpointerleave=()=>clearTimeout(pressTimer);

  function showFileMenu(path, isDir){
    if(!path&&path!=='')return;
    const modal=document.createElement('div');
    modal.className='action-popover';
    modal.innerHTML=`<div class="action-box"><strong>${esc(path||'/')}</strong><select id="fileActionSelect"><option value="rename">Rename</option><option value="delete">${isDir?'Delete folder':'Delete'}</option></select><div class="action-row"><button class="secondary" data-cancel>Cancel</button><button data-ok>Apply</button></div></div>`;
    document.body.appendChild(modal);
    const close=()=>modal.remove();
    modal.onclick=e=>{if(e.target===modal||e.target.closest('[data-cancel]'))close(); if(e.target.closest('[data-ok]')){const v=modal.querySelector('select').value; close(); if(v==='rename')renamePath(path); else deletePath(path)}};
  }

  async function openFile(path){
    try{const j=await api(`/api/projects/${projectId}/file/?path=${encodeURIComponent(path)}`); currentFile=path; $('#currentFile').textContent=path; $('#editor').value=j.content; showTab('editor')}
    catch(err){showError(err.message)}
  }
  async function renamePath(path){if(!path&&path!=='')return; if(!path)return; const oldName=path.split('/').pop(); const newName=prompt('Rename',oldName); if(!newName||newName===oldName)return; try{await api(`/api/projects/${projectId}/file/rename/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path,new_name:newName})}); loadTree(currentPath)}catch(err){showError(err.message)}}
  async function deletePath(path){if(!path)return; if(!confirm(`Delete "${path}"? This cannot be undone.`))return; try{await api(`/api/projects/${projectId}/file/delete/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})}); if(currentFile===path){currentFile=''; $('#currentFile').textContent='No file'; $('#editor').value=''; showTab('files')} loadTree(currentPath)}catch(err){showError(err.message)}}

  $('#newFileBtn').onclick=async()=>{
    const name=prompt('New file path (relative to project root):','');
    if(!name)return;
    try{await api(`/api/projects/${projectId}/file/new/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:name})}); await loadTree(currentPath); openFile(name)}
    catch(err){showError(err.message)}
  };

  $('#saveFile').onclick=async e=>{e.preventDefault(); if(!currentFile)return; try{await api(`/api/projects/${projectId}/file/save/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentFile,content:$('#editor').value})}); $('#currentFile').textContent=currentFile+' ✓'}catch(err){showError(err.message)}};

  const uploadPath=$('#uploadPath'), uploadFiles=$('#uploadFiles'), uploadBtn=$('#uploadBtn'), uploadSelected=$('#uploadSelected'), uploadStatus=$('#uploadStatus'), uploadDirSelect=$('#uploadDirSelect');
  function setUploadPath(path=''){if(uploadPath)uploadPath.value=path||''; if(uploadDirSelect)uploadDirSelect.value=[...uploadDirSelect.options].some(o=>o.value===(path||''))?(path||''):''}
  function updateUploadSelection(clearStatus=true){
    const files=[...(uploadFiles?.files||[])];
    if(uploadBtn) uploadBtn.disabled=files.length===0;
    if(uploadSelected) uploadSelected.textContent=files.length?`${files.length} file${files.length===1?'':'s'} selected: ${files.slice(0,3).map(f=>f.name).join(', ')}${files.length>3?' …':''}`:'No files selected';
    if(clearStatus&&uploadStatus) uploadStatus.textContent='';
  }
  async function loadUploadDirs(base='', depth=0, acc=['']){
    if(depth>5)return acc;
    const j=await api(`/api/projects/${projectId}/files/?path=${encodeURIComponent(base)}`);
    for(const i of j.items.filter(x=>x.is_dir)){
      const p=(base?base+'/':'')+i.name;
      acc.push(p);
      await loadUploadDirs(p,depth+1,acc);
    }
    return acc;
  }
  async function refreshUploadDirs(){
    if(!uploadDirSelect)return;
    try{
      const keep=uploadPath?.value||'';
      const dirs=await loadUploadDirs();
      uploadDirSelect.innerHTML=dirs.map(d=>`<option value="${esc(d)}">${d?esc(d):'/ project root'}</option>`).join('');
      setUploadPath(keep);
    }catch(err){showError(err.message)}
  }
  uploadFiles?.addEventListener('change',()=>updateUploadSelection());
  uploadDirSelect?.addEventListener('change',()=>setUploadPath(uploadDirSelect.value));
  uploadPath?.addEventListener('input',()=>{if(uploadDirSelect)uploadDirSelect.value=[...uploadDirSelect.options].some(o=>o.value===uploadPath.value)?uploadPath.value:''});
  refreshUploadDirs();
  $('#uploadForm').onsubmit=async e=>{
    e.preventDefault();
    if(!uploadFiles?.files?.length){showError('Choose one or more files to upload'); return}
    const fd=new FormData(e.target);
    if(uploadBtn) uploadBtn.disabled=true;
    if(uploadStatus) uploadStatus.textContent='Uploading…';
    try{
      const r=await fetch(`/api/projects/${projectId}/upload/`,{method:'POST',headers:{'X-CSRFToken':csrf()},body:fd});
      const j=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(j.error||'upload failed');
      if(uploadStatus) uploadStatus.textContent='Upload complete ✓';
      e.target.reset();
      setUploadPath(fd.get('path')||'');
      updateUploadSelection();
      await loadTree(currentPath);
      await refreshUploadDirs();
      showTab('files');
    }catch(err){if(uploadStatus) uploadStatus.textContent='Upload failed'; showError(err.message); updateUploadSelection(false)}
  };
  updateUploadSelection();
  function showTab(name){$$('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name)); $$('.tab-body').forEach(x=>x.classList.add('hidden')); $('#'+name+'Tab').classList.remove('hidden')}
  $$('[data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
  scrollChatEnd();

  function gitHint(err){
    const m=err.message||'';
    if(m.includes('not a git repository')) return 'Not a git repo — click "Init" to initialise one.';
    if(m.includes('nothing to commit')) return 'Nothing to commit — working tree is clean.';
    if(m.includes('Please tell me who you are')||m.includes('user.email')) return 'No git identity set. Run: git config --global user.email "you@example.com" && git config --global user.name "Name"';
    if(m.includes('Authentication failed')||m.includes('could not read Username')||m.includes('No such device or address')) return 'Push failed: authentication error. Switch to SSH remote: git remote set-url origin git@github.com:user/repo.git — or configure a credential store.';
    if(m.includes('Permission denied (publickey)')) return 'SSH key not accepted. Make sure ~/.ssh/id_ed25519 (or id_rsa) is added to your GitHub/GitLab account.';
    if(m.includes('Permission denied')) return 'Permission denied — check file ownership: ls -la in the project directory.';
    return m;
  }
  function gitShow(html,isErr=false){const el=$('#gitOutput'); el.innerHTML=html; el.className='diff-view'+(isErr?' git-err':'')}
  $('#gitInit').onclick=async()=>{
    try{
      const j=await api(`/api/projects/${projectId}/git/init/`,{method:'POST'});
      const out=j.output||'Repository initialised.';
      toast(out.includes('Reinitialized')?'Already a git repo — reinitialized.':'Repository initialised.');
      gitShow(esc(out));
    }catch(err){toast(gitHint(err),'err'); gitShow(esc(gitHint(err)),true)}
  };
  $('#gitDiff').onclick=async()=>{try{const j=await api(`/api/projects/${projectId}/git/diff/`); gitShow(renderDiff((j.status||'')+'\n'+(j.diff||'No diff')))}catch(err){gitShow(esc(gitHint(err)),true)}};
  $('#gitCommit').onclick=async()=>{
    let suggested='';
    try{
      const st=await api(`/api/projects/${projectId}/git/diff/`);
      const nFiles=(st.status||'').split('\n').filter(Boolean).length;
      const prompts=$$('.task-prompt').map(el=>el.textContent.replace(/^\$\s*/,'').trim()).filter(Boolean);
      if(prompts.length) suggested=prompts.slice(-3).join('; ');
      if(nFiles) suggested+=(suggested?' — ':'')+nFiles+' file'+(nFiles!==1?'s':'')+' changed';
    }catch{}
    const message=prompt('Commit message',suggested||'Update project');
    if(!message)return;
    try{
      const j=await api(`/api/projects/${projectId}/git/commit/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});
      toast('Committed.'); gitShow(esc(j.output||'Committed.'));
    }catch(err){toast(gitHint(err),'err'); gitShow(esc(gitHint(err)),true)}
  };
  $('#gitPush').onclick=async()=>{
    if(!confirm('Push current branch?'))return;
    try{
      const j=await api(`/api/projects/${projectId}/git/push/`,{method:'POST'});
      toast('Pushed.'); gitShow(esc(j.output||'Pushed.'));
    }catch(err){toast(gitHint(err),'err'); gitShow(esc(gitHint(err)),true)}
  };

  $$('[data-mobile-panel]').forEach(b=>b.onclick=()=>{
    const panel=b.dataset.mobilePanel;
    $$('.drawer,.chat-panel,.files-panel').forEach(x=>x.classList.remove('mobile-active'));
    $('.'+panel).classList.add('mobile-active');
    $$('[data-mobile-panel]').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
  });

  $$('.msg.assistant').forEach(el=>{el.innerHTML=md(el.dataset.raw||el.textContent)});
  $$('.msg.tool').forEach(el=>{
    const raw=el.dataset.raw||'';
    if(!raw)return;
    const f=renderStoredTool(raw);
    const d=document.createElement('details');
    d.className='msg tool'; d.innerHTML=`<summary>${f.titleHtml}</summary><div class="details-body">${f.body}</div>`;
    el.replaceWith(d);
  });
  loadTree();

  // User scroll tracking — scrolling up sets userScrolled; reaching bottom clears it
  {const m=$('#messages');if(m){let _pst=0;m.addEventListener('scroll',function(){const nB=this.scrollHeight-this.scrollTop-this.clientHeight<120;if(nB)userScrolled=false;else if(!_scrollLock&&this.scrollTop<_pst)userScrolled=true;_pst=this.scrollTop;},{passive:true});}}

  // Focus button — collapse all completed task groups and tool details
  let _fSaved=[];
  $('#focusBtn')?.addEventListener('click',function(){
    const on=this.classList.toggle('active');
    if(on){
      _fSaved=[];
      $$('#messages details').forEach(d=>{
        _fSaved.push({el:d,open:d.open});
        if(d.classList.contains('task-group')&&d.classList.contains('running'))return;
        d.open=false;
      });
    }else{_fSaved.forEach(({el,open})=>el.open=open);_fSaved=[];}
  });

  // Acknowledge button — create persistent checkpoint, reload page to show grouped history
  $('#ackBtn')?.addEventListener('click',()=>{
    if(piWorking){toast('Wait for the agent to finish before acknowledging.','err');return;}
    if(!ws||ws.readyState!==WebSocket.OPEN){toast('Not connected — wait a moment.','err');return;}
    const label=new Date().toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    ws.send(JSON.stringify({type:'checkpoint',label}));
    const btn=$('#ackBtn'); if(btn){btn.disabled=true;btn.textContent='saving…';}
  });

  // Play buttons — re-run incomplete / new tasks
  $$('.play-btn').forEach(btn=>{
    btn.addEventListener('click',e=>{
      e.stopPropagation();
      if(piWorking){toast('Wait for the current task to finish first.','err');return;}
      const p=btn.dataset.prompt;
      if(!p||!ws||ws.readyState!==WebSocket.OPEN){toast('Not connected — wait a moment.','err');return;}
      const tg=btn.closest('.task-group');
      if(tg){
        tg.classList.remove('incomplete','running');
        const b=tg.querySelector('.task-badge'); if(b){b.className='task-badge done';b.textContent='done';}
        tg.open=false; btn.style.display='none';
      }
      const ta=$('#prompt');
      ta.value=p; ta.style.height='auto'; ta.style.height=Math.min(ta.scrollHeight,240)+'px';
      userScrolled=false;
      $('#composer').requestSubmit();
    });
  });

  const memoryBtn=$('#memoryBtn');
  if(memoryBtn){
    const modal=$('#memoryModal'), ta=$('#memoryContent'), pathEl=$('#memoryPath');
    const url=memoryBtn.dataset.url;
    const open=async()=>{
      try{
        const r=await fetch(url,{headers:{'X-Requested-With':'XMLHttpRequest'},credentials:'same-origin'});
        const j=await r.json();
        ta.value=j.content||'';
        pathEl.textContent='';
        modal.classList.remove('hidden');
        ta.focus();
      }catch(e){toast('Could not load memory: '+e.message,'err');}
    };
    const close=()=>modal.classList.add('hidden');
    memoryBtn.onclick=open;
    $('#memoryCancel').onclick=close;
    $('#memorySave').onclick=async()=>{
      await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.cookie.match(/csrftoken=([^;]+)/)?.[1]||''},body:JSON.stringify({content:ta.value})});
      close();
      toast('Memory saved.');
    };
    modal.addEventListener('click',e=>{if(e.target===modal)close();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.classList.contains('hidden'))close();});
  }
}

if('serviceWorker' in navigator){
  navigator.serviceWorker.register('/service-worker.js',{scope:'/'}).then(reg=>{
    reg.update?.();
    if(reg.waiting) reg.waiting.postMessage({type:'SKIP_WAITING'});
  }).catch(()=>{});
}
