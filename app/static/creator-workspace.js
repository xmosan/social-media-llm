/* Presentation layer only. Source, renders, persistence and publishing stay in Studio. */
(function () {
  "use strict";
  const byId = (id) => document.getElementById(id),
    modal = byId("newPostModal");
  if (!modal) return;
  const usagePanel = byId("creatorUsage");
  let usageLoading = false;
  if (usagePanel) usagePanel.addEventListener("toggle", async () => {
    if (!usagePanel.open || usageLoading) return;
    usageLoading = true;
    const status = byId("creatorUsageStatus");
    status.textContent = "Checking allowance…";
    try {
      const response = await fetch("/api/studio/usage", { signal: AbortSignal.timeout(15000) });
      const usage = await response.json();
      if (!response.ok) throw new Error(usage.detail || "Could not check allowance.");
      const reset = new Date(usage.reset_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
      status.textContent = `${usage.generation_enabled ? "" : "AI generation is currently paused. "}${usage.images.used} of ${usage.images.limit} image attempts · ${usage.text.used} of ${usage.text.limit} writing attempts today. Resets ${reset}.`;
    } catch (error) {
      status.textContent = "Could not check allowance. Close and reopen this section to retry. Your saved work is available.";
    } finally {
      usageLoading = false;
    }
  });
  let entryMode = "guided",
    discovery = null,
    discoveryEpoch = 0,
    previousFocus = null,
    suggestion = null,
    undo = null,
    brandOnly = false;
  const section = byId("studioSection1");
  const sourceArea = document.createElement("div");
  sourceArea.id = "creatorSourceArea";
  while (section.firstChild) sourceArea.append(section.firstChild);
  section.append(sourceArea);
  // Keep optional writing preferences available without delaying source selection.
  const prefs = document.createElement("details");
  prefs.className = "cw-preferences";
  const prefsSummary = document.createElement("summary");
  prefsSummary.textContent = "Audience & writing preferences";
  prefs.append(prefsSummary);
  const sourceFields = byId("studioAccount").parentElement.parentElement;
  const extras = [...sourceFields.children].slice(1);
  sourceFields.append(prefs);
  for (const node of extras) prefs.append(node);
  // Choose a destination at Share; creating and saving need no social account.
  const accountField = byId("studioAccount").parentElement;
  accountField.querySelector("label").textContent = "Publish to Instagram";
  byId("studioInstagramPanel").prepend(accountField);
  byId("studioAccount").addEventListener("change", () => window.prepareShare());
  byId("studioTopic").setAttribute("aria-label", "Search Qur’an or Hadith");
  byId("studioAccount").setAttribute(
    "aria-label",
    "Instagram publishing account (optional for saving and export)",
  );
  byId("studioCustomPrompt").setAttribute(
    "aria-label",
    "Optional writing instructions",
  );
  byId("studioCaption").setAttribute("aria-label", "Social caption");
  byId("editSupporting").setAttribute("aria-label", "Separate reflection");

  const guided = document.createElement("section");
  guided.className = "cw-guided";
  guided.id = "creatorGuided";
  guided.innerHTML = `<p class="cw-eyebrow">Create with Sabeel</p><h4>What would you like to share?</h4><p>Describe the idea. Sabeel suggests sources to read and choose from, then helps you design your post.</p><label for="creatorIdea">Your idea<textarea id="creatorIdea" maxlength="600" placeholder="A gentle reminder for someone going through a difficult week"></textarea></label><label for="creatorSourceType">Find a source in<select id="creatorSourceType"><option value="quran">Qur’an</option><option value="hadith">Hadith</option></select></label><div class="cw-guided-actions"><button type="button" id="creatorDiscover" class="cw-primary">Find sources for my idea</button><button type="button" id="creatorDirect" class="cw-secondary">Choose a source</button></div><p id="creatorDiscoveryStatus" role="status" aria-live="polite"></p><div id="creatorDiscoveryResults" class="cw-guided-results"></div>`;
  section.prepend(guided);
  const notice = document.createElement("div");
  notice.id = "creatorNotice";
  notice.className = "cw-studio-alert hidden";
  notice.setAttribute("role", "alert");
  notice.tabIndex = -1;
  byId("composerForm").querySelector(".custom-scrollbar").prepend(notice);
  window.studioNotice = (message) => {
    notice.textContent = message;
    notice.classList.remove("hidden");
    notice.focus();
  };
  const modeBack = document.createElement("button");
  modeBack.type = "button";
  modeBack.className = "cw-secondary";
  modeBack.textContent = "← Start with an idea";
  modeBack.onclick = () => setEntry("guided");
  sourceArea.prepend(modeBack);
  sourceArea.querySelector("h4").tabIndex = -1;
  const firstRestore = sourceArea.querySelector(
    '[onclick="restoreStudioRecovery()"]',
  );
  if (firstRestore) firstRestore.remove();
  const visual = byId("studioSection2"),
    design = visual.querySelector(".cw-design-column"),
    words = byId("cardMessageWorkspace");
  const editDesign = document.createElement("button");
  editDesign.type = "button";
  editDesign.className = "cw-edit-design";
  editDesign.textContent = "Edit design ↓";
  editDesign.onclick = () => { showTool("design"); toolbar.scrollIntoView({block:"start",behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"}); };
  visual.querySelector(".cw-preview-column").prepend(editDesign);
  visual
    .querySelector(".cw-visual-grid")
    .prepend(visual.querySelector(".cw-preview-column"));
  const designPane = document.createElement("div");
  designPane.dataset.editorPane = "design";
  while (design.firstChild) designPane.append(design.firstChild);
  design.append(designPane);
  words.dataset.editorPane = "words";
  words.hidden = true;
  design.append(words);
  const toolbar = document.createElement("div");
  toolbar.className = "cw-editor-toolbar";
  toolbar.setAttribute("aria-label", "Editing tools");
  for (const [key, label] of [
    ["design", "Design"],
    ["words", "Source & reflection"],
  ]) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.creatorTool = key;
    b.textContent = label;
    b.onclick = () => {
      showTool(key);
      design
        .querySelector('[data-editor-pane="' + key + '"]')
        .scrollIntoView({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    };
    toolbar.append(b);
  }
  design.prepend(toolbar);
  // Enlarge the existing image and pager, preserving load/review tracking.
  const preview = byId("cardPreviewContainer"), pager = byId("sequenceNavigation");
  const previewHome = document.createComment("preview home");
  const pagerHome = document.createComment("pager home");
  preview.before(previewHome); pager.before(pagerHome);
  const reader = document.createElement("dialog");
  reader.id = "creatorPreviewDialog";
  reader.setAttribute("aria-label", "Review your images");
  reader.innerHTML = '<div class="cw-reader-heading"><strong>Review your images</strong><button type="button" class="cw-secondary">Back to editor</button></div><div class="cw-reader-pages"></div><p>Check each page at reading size. Return to the editor to confirm your review.</p>';
  modal.append(reader);
  const expand = document.createElement("button");
  expand.type = "button"; expand.id = "creatorExpandPreview";
  expand.className = "cw-edit-design"; expand.textContent = "Larger preview";
  editDesign.before(expand);
  expand.onclick = () => {
    if (byId("quoteCardPreview").classList.contains("hidden") || reader.open) return;
    reader.querySelector(".cw-reader-pages").append(preview, pager);
    reader.showModal();
  };
  reader.querySelector("button").onclick = () => reader.close();
  window.onCreatorPageChanged = () => { if (reader.open) reader.scrollTop = 0; };
  reader.addEventListener("close", () => {
    previewHome.after(preview); pagerHome.after(pager); expand.focus();
  });
  function showTool(key) {
    for (const pane of design.querySelectorAll("[data-editor-pane]"))
      pane.hidden = pane.dataset.editorPane !== key;
    words.classList.remove("hidden");
    for (const b of toolbar.children)
      b.setAttribute("aria-pressed", String(b.dataset.creatorTool === key));
  }
  showTool("design");
  const brand = byId("creatorBrandKit"),
    brandParent = brand.parentNode;
  // Per-post essentials come first. Workspace defaults live in the home brand editor.
  designPane.append(brand);
  const reading = byId("creatorReadingOptions");
  if(reading) designPane.append(reading);
  window.onCreatorDesignChanged = () => {
    const picker = byId("studioFamilyPicker"), family = byId("studioStyle").value;
    for (const option of [...picker.options]) if(option.dataset.legacy) option.remove();
    if(family && ![...picker.options].some(option => option.value === family)) {
      const saved = document.createElement("option");
      saved.value = family; saved.textContent = "Saved design"; saved.dataset.legacy = "true";
      picker.append(saved);
    }
    picker.value = family;
    const identity = byId("brandVisualIdentity").value.trim();
    byId("creatorVisualIdentityHint").textContent = identity
      ? "Your visual preferences apply. This direction takes priority."
      : "A fresh image each time. Set your visual preferences in Brand & typography.";
  };
  const brandHolder = document.createElement("div");
  brandHolder.hidden = true;
  section.append(brandHolder);
  function restoreBrand() {
    modal.setAttribute("aria-label", "Create a post");
    delete modal.dataset.brandOnly;
    if (brandOnly) {
      brandParent.insertBefore(brand, byId("creatorReadingOptions"));
      brand.open = false;
      brandOnly = false;
      brandHolder.hidden = true;
    }
  }
  function setEntry(mode) {
    entryMode = mode;
    guided.hidden = mode !== "guided";
    sourceArea.hidden = mode !== "direct";
    if (mode === "direct") byId("studioTopic").focus();
  }
  function cancelDiscovery() {
    discoveryEpoch++;
    discovery?.abort();
    discovery = null;
    byId("creatorDiscover").disabled = false;
  }
  window.readCreatorBrief = () => ({
    idea: byId("creatorIdea").value,
    sourceType: byId("creatorSourceType").value,
    mode: entryMode,
    audience: byId("studioAudience").value,
    purpose: byId("studioPurpose").value,
    instructions: byId("studioCustomPrompt").value,
    tone: byId("studioTone").value,
    reflection: byId("includeStudioReflection").checked,
  });
  window.restoreCreatorBrief = (data) => {
    if (!data) return;
    for (const [field, id] of [
      ["audience", "studioAudience"],
      ["purpose", "studioPurpose"],
      ["instructions", "studioCustomPrompt"],
      ["tone", "studioTone"],
    ])
      if (data[field] !== undefined) byId(id).value = data[field];
    if (data.reflection !== undefined)
      byId("includeStudioReflection").checked = data.reflection;
    byId("creatorIdea").value = data.idea || "";
    byId("creatorSourceType").value =
      data.sourceType === "hadith" ? "hadith" : "quran";
    setEntry(data.mode === "direct" ? "direct" : "guided");
  };
  window.resetCreatorEntry = () => {
    cancelDiscovery();
    suggestion = undo = null;
    byId("creatorSuggestion")?.remove();
    byId("studioCaption").parentNode.hidden = false;
    restoreBrand();
    byId("creatorIdea").value = "";
    byId("creatorDiscoveryResults").replaceChildren();
    byId("creatorDiscoveryStatus").textContent = "";
    byId("creatorSaveState").textContent = "";
    window.creatorSaveBusy(false);
    byId("studioSaveStatus").textContent = "";
    modal.querySelector(".cw-draft-menu").open = false;
    notice.classList.add("hidden");
    byId("captionResultArea").classList.remove("hidden");
    byId("btnGenerateCaption").disabled = false;
    setEntry("guided");
  };
  const oldOpen = window.openNewPostModal,
    oldClose = window.closeNewPostModal;
  function isolatePage(on) {
    for (const el of document.querySelectorAll(
      "body>main,body>nav,body>header",
    ))
      el.inert = on;
    document.body.style.overflow = on ? "hidden" : "";
  }
  window.openNewPostModal = function () {
    previousFocus = document.activeElement;
    oldOpen();
    isolatePage(true);
    byId("creatorIdea").focus();
  };
  window.closeNewPostModal = function () {
    if (reader.open) reader.close();
    document.getElementById("studioFamilyDialog")?.close();
    if (oldClose() === false) return;
    cancelDiscovery();
    isolatePage(false);
    previousFocus?.focus();
    refreshRecovery();
  };
  window.startCreatorIdea = (idea) => {
    window.openNewPostModal();
    byId("creatorIdea").value = idea;
    window.rememberStudio();
  };
  window.openCreatorSource = () => {
    window.openNewPostModal();
    setEntry("direct");
  };
  window.openCreatorBrand = () => {
    window.openNewPostModal();
    brandOnly = true;
    modal.dataset.brandOnly = "true";
    modal.setAttribute("aria-label", "Edit your brand kit");
    guided.hidden = sourceArea.hidden = true;
    brandHolder.hidden = false;
    brandHolder.append(brand);
    brand.open = true;
    brand.querySelector("select").focus();
  };
  window.resumeCreatorRecovery = async (key = null) => {
    window.openNewPostModal();
    await window.restoreStudioRecovery(key);
  };
  window.clearCreatorSource = () => {
    window.onSourceInput();
    byId("studioTopic").focus();
    window.rememberStudio();
  };
  window.onCreatorVisualReady = () => {
    if (byId('newPostModal').dataset.step !== '2') return;
    byId("cardPreviewContainer").scrollIntoView({
      block: "start",
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  };
  window.onCreatorSection = (step) => {
    notice.classList.add("hidden");
    if (brandOnly && step !== 1) restoreBrand();
    if (step === 2) { showTool("design"); brand.open = false; window.updateStudioVisualAction?.(); }
    if (step === 3) byId("captionResultArea").classList.remove("hidden");
    byId("composerForm").querySelector(".custom-scrollbar").scrollTop = 0;
  };
  byId("creatorDirect").onclick = () => setEntry("direct");
  for (const id of ["creatorIdea", "creatorSourceType"])
    byId(id).addEventListener("input", () => {
      cancelDiscovery();
      byId("creatorDiscoveryStatus").textContent = "";
      byId("creatorDiscoveryResults").replaceChildren();
      window.rememberStudio();
    });
  // Source discovery recovery: no invented text, automatic retries or unrelated replacements.
  function showDiscoveryRecovery(type, terms = []) {
    const results=byId("creatorDiscoveryResults"), panel=document.createElement("section");
    panel.className="cw-search-recovery";
    const title=document.createElement("h5");title.textContent="Let’s try another way";
    const note=document.createElement("p");note.textContent="Your idea is kept. Browse a broader topic or search a reference; you will still choose and review the source.";
    const label=document.createElement("label");label.textContent="One simple topic";
    const input=document.createElement("input");input.type="text";input.maxLength=100;input.placeholder="For example: patience or fasting";
    input.value=terms.find(term=>typeof term==='string' && /^[A-Za-z]{2,32}$/.test(term)) || '';
    label.append(input);
    const direct = query => {
      const brief=window.readCreatorBrief();window.switchSourceTab(type);
      window.restoreCreatorBrief({...brief,mode:'direct'});setEntry('direct');
      byId('studioTopic').value=query;window.rememberStudio();
      if(query) window.onSourceInput();
    };
    const browse=document.createElement("button");browse.type='button';browse.className='cw-primary';browse.textContent='Search the source library';
    browse.onclick=()=>{if(input.value.trim().length<2){input.focus();return;}direct(input.value.trim());};
    input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();browse.click();}};
    const swap=document.createElement("button");swap.type='button';swap.className='cw-secondary';swap.textContent=type==='quran' ? 'Try Hadith for this idea' : 'Try Qur’an for this idea';
    swap.onclick=()=>{byId('creatorSourceType').value=type==='quran' ? 'hadith' : 'quran';byId('creatorDiscover').click();};
    const reference=document.createElement("button");reference.type='button';reference.className='cw-secondary';reference.textContent='Search an exact reference';reference.onclick=()=>direct('');
    panel.append(title,note,label,browse,swap,reference);results.append(panel);
  }
  // End source discovery recovery.
  byId("creatorDiscover").onclick = async () => {
    if (discovery) return;
    const idea = byId("creatorIdea").value.trim(),
      type = byId("creatorSourceType").value,
      status = byId("creatorDiscoveryStatus"),
      results = byId("creatorDiscoveryResults");
    if (idea.length < 3) {
      status.textContent =
        "Write a little more about the reminder you want to create.";
      byId("creatorIdea").focus();
      return;
    }
    window.rememberStudio();
    const epoch = ++discoveryEpoch;
    discovery = new AbortController();
    const controller = discovery;
    const timer = setTimeout(() => controller.abort(), 65000);
    byId("creatorDiscover").disabled = true;
    results.replaceChildren();
    status.textContent =
      "Finding sources to consider… You will choose what fits.";
    try {
      const res = await fetch("/api/studio/discover-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea, source_type: type }),
        signal: controller.signal,
      });
      const data = await res.json();
      if (epoch !== discoveryEpoch) return;
      if (!res.ok)
        throw Error(data.detail || "Source suggestions are unavailable.");
      status.textContent = data.sources?.length
        ? data.notice
        : "No close match in this search. Your idea is still here.";
      if(!data.sources?.length) showDiscoveryRecovery(type,data.terms || []);
      for (const source of data.sources || []) {
        const card = document.createElement("article");
        card.className = "cw-candidate";
        const title = document.createElement("h5");
        title.textContent = source.reference;
        const text = document.createElement("p");
        text.textContent = source.translation_text;
        const details = document.createElement("details"),
          summary = document.createElement("summary");
        summary.textContent = "Arabic & source details";
        details.append(summary);
        const ar = document.createElement("p");
        ar.lang = "ar";
        ar.dir = "rtl";
        ar.textContent = source.arabic_text || "Arabic not returned";
        details.append(ar);
        const attribution = document.createElement("p");
        attribution.textContent =
          type === "hadith"
            ? `Narrator: ${source.narrator || "Not returned"} · Grade: ${source.grade || "Not returned"}`
            : "From the connected Qur’an library. Review the surrounding verses for context.";
        details.append(attribution);
        const choose = document.createElement("button");
        choose.type = "button";
        choose.textContent = "Use this source";
        choose.onclick = async () => {
          const brief = window.readCreatorBrief();
          window.switchSourceTab(type);
          window.restoreCreatorBrief(brief);
          if (type === "quran")
            window.selectAyah(
              source.id,
              source.reference,
              source.translation_text,
              source.arabic_text,
            );
          else {
            const dataElement = document.createElement("button");
            dataElement.setAttribute("data-meta", JSON.stringify(source));
            window.selectHadithFromEl(dataElement);
          }
          setEntry("direct");
          window.rememberStudio();
          await window.buildCardMessage();
        };
        card.append(title, text, details, choose);
        results.append(card);
      }
    } catch (e) {
      if (epoch === discoveryEpoch) {
        status.textContent = e.name === "AbortError"
          ? "Suggestions took too long. Your idea is kept. You can search the library directly below."
          : e.message;
        showDiscoveryRecovery(type);
      }
    } finally {
      clearTimeout(timer);
      if (epoch === discoveryEpoch) {
        discovery = null;
        byId("creatorDiscover").disabled = false;
      }
    }
  };
  function recoveryKey() {
    return "sabeel-studio-v2:" + modal.dataset.workspace;
  }
  function refreshRecovery() {
    try {
      const saved = JSON.parse(localStorage.getItem(recoveryKey()) || "null"),
        banner = byId("creatorRecovery");
      if (!banner) return;
      banner.classList.toggle("hidden", !saved);
      if (saved)
        byId("creatorRecoverySummary").textContent =
          (saved.entry?.idea ||
            saved.payload?.source_metadata?.reference ||
            "Unfinished post") + " · on this device";
      byId("creatorOtherDrafts")?.remove();
      const drafts = JSON.parse(
        localStorage.getItem(recoveryKey() + ":drafts") || "[]",
      ).filter((d) => d.payload?.draft_key !== saved?.payload?.draft_key);
      if (drafts.length) {
        const list = document.createElement("details");
        list.id = "creatorOtherDrafts";
        list.className = "cw-local-drafts";
        const heading = document.createElement("summary");
        heading.textContent = `Other drafts on this device (${drafts.length})`;
        list.append(heading);
        for (const draft of drafts.slice().reverse()) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent =
            draft.entry?.idea ||
            draft.payload?.source_metadata?.reference ||
            "Unfinished post";
          button.onclick = () =>
            window.resumeCreatorRecovery(draft.payload?.draft_key || "legacy");
          list.append(button);
        }
        banner.after(list);
      }
    } catch (_) {}
  }
  window.onCreatorBrandSaved = (kit) => {
    if (byId("workspaceBrandSummary"))
      byId("workspaceBrandSummary").textContent =
        (kit.signature || "Add your signature") +
        " · " +
        (kit.series_name || "Your next series");
    if (byId("workspaceBrandSignature"))
      byId("workspaceBrandSignature").textContent =
        kit.signature || "Add your signature";
  };
  let savedStudioPayload = null;
  window.creatorCloudSaved = () => {
    savedStudioPayload = JSON.stringify(window.studioShareSnapshot?.().payload);
    byId("creatorSaveState").textContent = "Saved to your workspace";
  };
  window.creatorSaveBusy = (busy) => {
    const button = byId("studioSaveDraftButton");
    button.disabled = busy;
    button.textContent = busy ? "Saving…" : "Save draft";
  };
  window.creatorRecoveryStatus = (ok) => {
    byId("studioSaveStatus").textContent = "";
    const cloudSaved = savedStudioPayload && savedStudioPayload === JSON.stringify(window.studioShareSnapshot?.().payload);
    const pinDirty = window.readStudioSharing?.().pin?.dirty;
    byId("creatorSaveState").textContent = !ok
      ? "Recovery could not be saved on this device. Keep this window open."
      : cloudSaved && !pinDirty ? "Saved to your workspace" : "Changes kept on this device";
  };
  // Persist every editable field, including early ideas. Never write when Studio is closed.
  modal.addEventListener("input", (e) => {
    if (e.target.id === "studioCaption") return;
    if (!modal.classList.contains("hidden")) window.rememberStudio();
  });
  modal.addEventListener("change", () => {
    if (!modal.classList.contains("hidden")) window.rememberStudio();
  });
  window.addEventListener("pagehide", () => {
    if (!modal.classList.contains("hidden")) window.rememberStudio();
  });
  window.clearCreatorSuggestion = () => {
    suggestion = undo = null;
    byId("creatorSuggestion")?.remove();
    byId("studioCaption").parentNode.hidden = false;
  };
  function suggestionTarget(kind) {
    return byId(kind === "caption" ? "studioCaption" : "editSupporting");
  }
  window.offerCreatorSuggestion = (kind, before, after) => {
    suggestion = {
      kind,
      before,
      after,
      source: JSON.stringify(window.studioSourceContext),
    };
    byId("creatorSuggestion")?.remove();
    byId("studioCaption").parentNode.hidden = false;
    const panel = document.createElement("section");
    panel.id = "creatorSuggestion";
    panel.dataset.pending = "true";
    panel.className = "cw-suggestion";
    panel.tabIndex = -1;
    const heading = document.createElement("h5");
    heading.textContent =
      kind === "caption"
        ? "Caption suggestion"
        : "Separate reflection suggestion";
    panel.append(heading);
    for (const [label, value] of [
      ["Your version", before || "Nothing written yet"],
      ["Sabeel’s suggestion", after],
    ]) {
      const h = document.createElement("p");
      h.textContent = label;
      const content = document.createElement("pre");
      content.textContent = value;
      if (label === "Your version") {
        if (before) { const old = document.createElement("details"), summary = document.createElement("summary"); summary.textContent = "Compare with my current caption"; old.append(summary, content); panel.append(old); }
      } else { panel.append(content); }
    }
    const actions = document.createElement("div");
    actions.className = "cw-guided-actions";
    for (const [label, fn] of [
      [
        "Keep mine",
        () => {
          panel.remove();
          byId("studioCaption").parentNode.hidden = false;
          suggestion = null;
        },
      ],
      ["Use suggestion", applySuggestion],
    ]) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = label === "Keep mine" ? "cw-secondary" : "cw-primary";
      b.textContent = label;
      b.onclick = fn;
      actions.append(b);
    }
    panel.append(actions);
    if (kind === "caption") {
      byId("captionResultArea").classList.remove("hidden");
      byId("studioCaption").parentNode.before(panel);
    } else {
      showTool("words");
      byId("editSupporting").parentNode.before(panel);
    }
    if (kind === "caption") byId("studioCaption").parentNode.hidden = true;
    panel.focus();
  };
  function applySuggestion() {
    if (!suggestion) return;
    const s = suggestion,
      target = suggestionTarget(s.kind);
    if (
      target.value !== s.before ||
      JSON.stringify(window.studioSourceContext) !== s.source
    ) {
      window.studioNotice(
        "Your writing or source changed. This suggestion was not applied. Ask Sabeel again with your latest edit.",
      );
      return;
    }
    target.parentNode.hidden = false;
    target.value = s.after;
    undo = s;
    suggestion = null;
    if (s.kind === "caption") window.captionChanged();
    else window.updateStudioCardFromUI();
    window.rememberStudio();
    const p = byId("creatorSuggestion");
    p.dataset.pending = "false";
    p.replaceChildren();
    const note = document.createElement("p");
    note.textContent = "Suggestion applied. Your source is unchanged.";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "cw-secondary";
    b.textContent = "Undo";
    b.onclick = () => {
      if (!undo) return;
      const t = suggestionTarget(undo.kind);
      if (
        t.value !== undo.after ||
        JSON.stringify(window.studioSourceContext) !== undo.source
      ) {
        window.studioNotice(
          "You have made newer edits. Undo will not overwrite them.",
        );
        return;
      }
      t.value = undo.before;
      if (undo.kind === "caption") window.captionChanged();
      else window.updateStudioCardFromUI();
      window.rememberStudio();
      undo = null;
      p.remove();
    };
    p.append(note, b);
  }
  // Focus stays in the editor; Escape closes without discarding recovery.
  modal.addEventListener("keydown", (e) => {
    if (reader.open) return; // Native dialog handles Escape and focus containment.
    if (!byId("editPostModal").classList.contains("hidden")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      window.closeNewPostModal();
      return;
    }
    if (e.key !== "Tab") return;
    const items = [
      ...modal.querySelectorAll(
        'button,a[href],input,select,textarea,summary,[tabindex="0"]',
      ),
    ].filter((el) => !el.disabled && el.getClientRects().length);
    const first = items[0],
      last = items.at(-1);
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  });
  for (const a of document.querySelectorAll(
    ".cw-bottom-nav a,body>nav .nav-link",
  )) {
    const u = new URL(a.href);
    const active =
      u.pathname === location.pathname && u.search === location.search;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
  }
  for (const el of modal.querySelectorAll(".tone-card")) {
    el.setAttribute("role", "button");
    el.tabIndex = 0;
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        el.click();
      }
    });
  }
  byId("editHeadline").setAttribute("aria-label", "Exact source translation");
  byId("editEyebrow").setAttribute("aria-label", "Source reference");
  setEntry("guided");
  refreshRecovery();
})();
