// Small helper JS. Real Chart.js is expected at chart.min.js (include via CDN in production).
document.addEventListener('DOMContentLoaded', function(){
  // Intercept clicks on links with data-ajax to perform SPA-like navigation
  function ajaxNavigate(url, replace){
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(r => r.text())
      .then(html => {
        // parse response and extract inner of main-content
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        const newMain = tmp.querySelector('#main-content');
        if(newMain){
          const target = document.querySelector('#main-content');
          target.innerHTML = newMain.innerHTML;
          // execute inline scripts in the new content
          target.querySelectorAll('script').forEach(s => {
            const ns = document.createElement('script');
            if(s.src) ns.src = s.src;
            else ns.textContent = s.textContent;
            document.body.appendChild(ns);
            ns.parentNode.removeChild(ns);
          });
          if(!replace) history.pushState({ url: url }, '', url);
          // re-initialize autocomplete for student input if present
          initStudentAutocomplete();
          // If the page defines a pageInit function, call it to initialize page-specific JS (charts, widgets)
          try{ if(window.pageInit && typeof window.pageInit === 'function') window.pageInit(); }catch(e){ console.error('pageInit error', e); }
        } else {
          // fallback full load
          window.location = url;
        }
      })
      .catch(err => { console.error(err); window.location = url; });
  }

  document.body.addEventListener('click', function(e){
    const a = e.target.closest('a[data-ajax]');
    if(a){
      e.preventDefault();
      ajaxNavigate(a.href, false);
    }
  });

  window.addEventListener('popstate', function(e){
    if(e.state && e.state.url){
      ajaxNavigate(e.state.url, true);
    }
  });
});

// Autocomplete helper: attach to input#student-name and populate datalist#students
function initStudentAutocomplete(){
  const input = document.querySelector('#student-name-input');
  const container = document.querySelector('#student-suggestions');
  if(!input || !container) return;
  let timer = null;
  let items = [];
  let index = -1;

  function clear(){ container.classList.add('hidden'); container.innerHTML = ''; items = []; index = -1; input.setAttribute('aria-expanded','false'); }

  function render(names){
    container.innerHTML = '';
    items = names.map((n,i)=>{
      const div = document.createElement('div');
      div.className = 'autocomplete-item flex justify-between items-center';
      div.tabIndex = 0;
      div.setAttribute('role','option');
      div.setAttribute('data-index', i);
      div.innerHTML = `<span>${n}</span>`;
      div.addEventListener('click', (e)=>{ e.preventDefault(); e.stopPropagation(); input.value = n; clear(); input.focus(); });
      div.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ e.preventDefault(); e.stopPropagation(); input.value = n; clear(); input.focus(); } });
      container.appendChild(div);
      return div;
    });
    if(items.length){ container.classList.remove('hidden'); input.setAttribute('aria-expanded','true'); }
    else clear();
    index = -1;
  }

  input.addEventListener('input', function(){
    clearTimeout(timer);
    const q = input.value.trim();
    if(q.length < 1){ clear(); return; }
    timer = setTimeout(()=>{
      fetch('/api/students?q=' + encodeURIComponent(q))
        .then(r=>r.json())
        .then(names=> render(names));
    }, 200);
  });

  input.addEventListener('keydown', function(e){
    if(e.key === 'Tab'){
      // If suggestions visible, Tab should focus first suggestion (selectable), not move out
      if(!container.classList.contains('hidden') && items.length){
        e.preventDefault(); index = 0; items.forEach((it,i)=> it.classList.toggle('active', i===index)); items[0].focus();
        return;
      }
      return; // allow normal tab if no suggestions
    }
    if(container.classList.contains('hidden')) return;
    if(e.key === 'ArrowDown'){
      e.preventDefault(); index = Math.min(items.length -1, index+1); items.forEach((it,i)=> it.classList.toggle('active', i===index)); if(items[index]) items[index].focus();
    } else if(e.key === 'ArrowUp'){
      e.preventDefault(); index = Math.max(0, index-1); items.forEach((it,i)=> it.classList.toggle('active', i===index)); if(items[index]) items[index].focus();
    } else if(e.key === 'Enter'){
      // If suggestions exist, the first Enter should select (if none active, pick first). Do not submit the form.
      if(items.length){
        e.preventDefault(); e.stopPropagation();
        if(index >=0 && items[index]){ input.value = items[index].innerText.trim(); }
        else { input.value = items[0].innerText.trim(); }
        clear();
        return;
      }
      // else allow form submission
    } else if(e.key === 'Escape'){
      clear();
    }
  });

  document.addEventListener('click', function(e){ if(!container.contains(e.target) && e.target !== input) clear(); });
}

document.addEventListener('DOMContentLoaded', initStudentAutocomplete);
// If a page defines a pageInit function (for charts/widgets), call it on full page load as well
document.addEventListener('DOMContentLoaded', function(){ try{ if(window.pageInit && typeof window.pageInit === 'function') window.pageInit(); }catch(e){ console.error('pageInit error', e); } });

// Toggle dropdown menu for Google Calendar
function toggleCalendarMenu() {
  const menu = document.getElementById('calendarMenu');
  menu.classList.toggle('hidden');
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
  const menu = document.getElementById('calendarMenu');
  const button = event.target.closest('button[onclick="toggleCalendarMenu()"]');
  if (menu && !menu.contains(event.target) && !button) {
    menu.classList.add('hidden');
  }
});
