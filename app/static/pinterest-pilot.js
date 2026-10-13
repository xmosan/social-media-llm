/* Owner-only connection checks. No publication or credential access. */
(() => {
    const byId=id=>document.getElementById(id);
    let bookmark=null,busy=false;
    const status=message=>{byId('boardStatus').textContent=message;};
    async function request(url,options={}) {
        const response=await fetch(url,{credentials:'same-origin',signal:AbortSignal.timeout(45000),...options});
        const data=await response.json();
        if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'The request could not be completed.');
        return data;
    }
    async function load(more=false) {
        if(busy)return;busy=true;
        byId('loadBoards').disabled=true;byId('moreBoards').disabled=true;
        status('Loading your boards…');
        try {
            const data=await request('/api/pinterest/boards'+(more&&bookmark?'?bookmark='+encodeURIComponent(bookmark):''));
            const select=byId('boardChoice');
            if(!more)select.replaceChildren();
            for(const item of data.items) {
                if([...select.options].some(o=>o.value===item.id))continue;
                const option=document.createElement('option');option.value=item.id;option.textContent=item.name;select.append(option);
            }
            bookmark=data.bookmark||null;
            byId('moreBoards').hidden=!bookmark;byId('boardForm').hidden=!select.options.length;
            status(select.options.length?'Choose a board, then confirm below.':bookmark?'No boards on this page. Load the next page.':'No public boards owned by this account were returned.');
        } catch(error) {status(error.name==='TimeoutError'?'Pinterest took too long. Try loading the boards again.':error.message);}
        finally {busy=false;byId('loadBoards').disabled=false;byId('moreBoards').disabled=false;}
    }
    byId('loadBoards')?.addEventListener('click',()=>load());
    byId('moreBoards')?.addEventListener('click',()=>load(true));
    byId('boardForm')?.addEventListener('submit',async event=>{
        event.preventDefault();if(busy)return;busy=true;
        const button=event.currentTarget.querySelector('button');button.disabled=true;
        const selected=byId('boardChoice').selectedOptions[0];
        try {
            if(!selected)throw new Error('Choose a board first.');
            await request('/api/pinterest/board',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({board_id:selected.value})});
            byId('chosenBoard').textContent='Selected board: '+selected.textContent;status('Board saved. Nothing has been published.');
        } catch(error) {status(error.name==='TimeoutError'?'The result was not received. Reload this page to check the saved board.':error.message);}
        finally {busy=false;button.disabled=false;}
    });
    document.querySelectorAll('form[method="post"]').forEach(form=>form.addEventListener('submit',()=>{form.querySelector('button').disabled=true;}));
})();
