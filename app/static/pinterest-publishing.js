/* Owner-only, explicit review; no auto-publish, auto-retry or schedule. */
(() => {
    const el=id=>document.getElementById(id);
    let busy=false,receipt=null,copy=null,reviewedPost=null,posts=[],imageReady=false;
    const message=text=>{el('pinStatus').textContent=text;};
    const endpoint=suffix=>'/api/pinterest/posts/'+encodeURIComponent(el('pinPost').value)+(suffix||'');
    async function request(url,options={}) {
        const response=await fetch(url,{credentials:'same-origin',signal:AbortSignal.timeout(120000),...options});
        const data=await response.json();
        if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'The request could not be completed. Reload to check the saved result.');
        return data;
    }
    function pending(value) {
        busy=value;
        ['loadPinPosts','pinPost','pinTitle','pinDescription','pinAlt','pinAI','reviewPin','verifyPin'].forEach(id=>el(id).disabled=value);
        el('publishPin').disabled=value||!receipt||!imageReady||!el('pinReviewed').checked;
    }
    function resetReview() {receipt=null;copy=null;reviewedPost=null;imageReady=false;el('pinReviewed').checked=false;el('pinReviewed').disabled=true;el('pinReview').hidden=true;el('publishPin').disabled=true;}
    function result(data) {
        const published=data.status==='published';
        el('pinLink').hidden=!published;el('verifyPin').hidden=!published;
        if(published)el('pinLink').href=data.url;
        message(published?'Pinterest confirmed this Pin. Its ID is saved; repeating the request will not create another.':
            ['publishing','unknown'].includes(data.status)?'Delivery is pending or uncertain. Do not send again; check Pinterest and the saved result.':
            data.error||'Ready to prepare a reviewed test Pin.');
        if(['published','publishing','unknown'].includes(data.status))resetReview();
    }
    async function selectPost() {
        resetReview();el('pinLink').hidden=true;el('verifyPin').hidden=true;
        const post=posts.find(p=>String(p.id)===el('pinPost').value);
        el('pinTitle').value=post?.reference||'';el('pinDescription').value=post?.reference||'';
        el('pinAlt').value=post?'Arabic and English source card: '+post.reference+'.':'';el('pinAI').value='';
        if(post)result(await request(endpoint()));
    }
    el('loadPinPosts').addEventListener('click',async()=>{
        if(busy)return;pending(true);resetReview();message('Loading saved cards…');
        try {
            posts=(await request('/api/pinterest/posts')).items;el('pinPost').replaceChildren();
            for(const post of posts){const option=document.createElement('option');option.value=String(post.id);option.textContent='#'+post.id+' · '+post.reference;el('pinPost').append(option);}
            el('pinCopyForm').hidden=!posts.length;
            if(posts.length)await selectPost();else message('No single-card feed posts found. Create and review one in Studio first.');
        }catch(error){message(error.message);}finally{pending(false);}
    });
    el('pinPost').addEventListener('change',async()=>{
        if(busy)return;pending(true);
        try{await selectPost();}catch(error){message(error.message);}finally{pending(false);}
    });
    ['pinTitle','pinDescription','pinAlt','pinAI'].forEach(id=>el(id).addEventListener('input',resetReview));
    el('pinCopyForm').addEventListener('submit',async event=>{
        event.preventDefault();if(busy)return;pending(true);resetReview();message('Checking the source and final image…');
        try{
            if(!['yes','no'].includes(el('pinAI').value))throw Error('Choose the AI disclosure.');
            const draft={title:el('pinTitle').value,description:el('pinDescription').value,alt_text:el('pinAlt').value,ai_modified:el('pinAI').value==='yes',link:null};
            const data=await request(endpoint('/review'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft)});
            receipt=data.receipt;copy=draft;reviewedPost=el('pinPost').value;
            const currentReceipt=receipt;
            el('pinImage').onload=()=>{if(receipt!==currentReceipt)return;imageReady=el('pinImage').naturalWidth>0;el('pinReviewed').disabled=!imageReady;};
            el('pinImage').onerror=()=>{if(receipt!==currentReceipt)return;resetReview();message('The preview image did not load. Preview again before approving this Pin.');};
            el('pinImage').src=data.image_url;el('pinDestination').textContent='Destination: @'+data.username+' → '+data.board_name;
            el('pinReference').textContent=data.source_reference;el('pinArabic').textContent=data.arabic;el('pinTranslation').textContent=data.translation;
            el('pinSourceDetails').textContent=data.source_details||'';
            el('pinReflection').textContent=data.reflection;el('pinReflectionBlock').hidden=!data.reflection;
            el('pinCopyPreview').textContent=draft.title+'\n\n'+draft.description+'\n\nImage description: '+draft.alt_text+'\nAI disclosure: '+(draft.ai_modified?'Yes':'No');
            el('pinReview').hidden=false;message('Review the complete card and copy below. Nothing has been sent.');
        }catch(error){message(error.message);}finally{pending(false);}
    });
    el('pinReviewed').addEventListener('change',()=>{el('publishPin').disabled=busy||!receipt||!imageReady||!el('pinReviewed').checked;});
    el('publishPin').addEventListener('click',async()=>{
        if(busy||!receipt||!imageReady||!el('pinReviewed').checked||reviewedPost!==el('pinPost').value)return;
        const body={...copy,receipt,reviewed:true};pending(true);message('Sending one reviewed test Pin…');
        try{result(await request(endpoint('/publish'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}));}
        catch(error){resetReview();message(error.name==='TimeoutError'?'The result was not received. Reload saved cards before doing anything else.':error.message);}
        finally{resetReview();pending(false);}
    });
    el('verifyPin').addEventListener('click',async()=>{
        if(busy)return;pending(true);
        try{const data=await request(endpoint('/verify'));result(data);message(data.message);}catch(error){message(error.message);}finally{pending(false);}
    });
})();
