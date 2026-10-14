/* Local view filters do not alter saved posts, schedules or publishing state. */
(() => {
  const filters=[...document.querySelectorAll('[data-post-filter]')], search=document.getElementById('workspacePostSearch');
  let filter='all';
  function posts() {
    let count=0;const query=(search?.value || '').trim().toLowerCase();
    for(const post of document.querySelectorAll('.cw-post-gallery [data-post-category]')) {
      const show=(filter==='all'||post.dataset.postCategory===filter)&&post.dataset.postSearch.includes(query);
      post.hidden=!show;if(show)count++;
    }
    const empty=document.getElementById('workspacePostEmpty');if(empty)empty.hidden=count>0;
  }
  filters.forEach(button=>button.onclick=()=>{filter=button.dataset.postFilter;filters.forEach(b=>b.setAttribute('aria-pressed',String(b===button)));posts();});
  search?.addEventListener('input',posts);
  const days=[...document.querySelectorAll('[data-plan-day]')];
  function plan(value) {
    let count=0;
    for(const item of document.querySelectorAll('[data-plan-date]')) {
      const show=value==='upcoming'?item.dataset.planUpcoming==='true':item.dataset.planDate===value;
      item.hidden=!show;if(show)count++;
    }
    days.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.planDay===value)));
    const empty=document.getElementById('workspacePlanEmpty');if(empty)empty.hidden=count>0;
  }
  days.forEach(button=>button.onclick=()=>plan(button.dataset.planDay));if(days.length)plan('upcoming');
  // Put device recovery in one disclosure, preserving every archived entry.
  window.organizeWorkspaceRecovery=()=>{
    const recovery=document.getElementById('creatorRecovery'), drafts=document.getElementById('creatorOtherDrafts');
    if(!recovery || !drafts)return;
    // Keep a disclosure reachable even if there is no current draft.
    if(!recovery.classList.contains('hidden'))recovery.append(drafts);
  };
  window.organizeWorkspaceRecovery();
})();
