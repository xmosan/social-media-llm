"""Small, server-rendered creator workspace. Actions use the canonical Studio."""
import html
import json
from urllib.parse import urlsplit
from app.services.brand_kit import PALETTES


def escape(value):
    return html.escape(str(value or ""), quote=True)


def post_card(post):
    flags = post.flags or {}
    pages = (flags.get("media_manifest") or {}).get("pages", [])
    title = post.source_reference or post.topic or "Untitled reminder"
    labels = {"draft": "Draft", "drafted": "Draft", "ready": "Ready to review", "scheduled": "Scheduled",
              "published": "Published", "shared": "Published", "publish_unknown": "Check publishing outcome",
              "publish_partial": "Stories partly published", "publishing": "Publishing", "failed": "Needs attention",
              "needs_review": "Needs review"}
    status = labels.get(post.status, "Needs review")
    format_label = "Stories" if post.post_format == "story_9_16" else "Feed"
    arguments = escape(json.dumps([post.id, post.caption or "", post.scheduled_time.isoformat() if post.scheduled_time else "", post.status]))
    image = f'<span class="cw-placeholder" aria-hidden="true">S</span>'
    if post.media_url and urlsplit(post.media_url).scheme == "https":
        image = f'<img src="{escape(post.media_url)}" alt="" loading="lazy">'
    direct = post.status in {'draft', 'drafted', 'ready'} and bool(getattr(post, 'card_message', None)) and bool(pages)
    handler = f'resumeStudioPost({post.id})' if direct else f'openEditPostModal(...{arguments})'
    pin_status = (flags.get("pinterest_publication") or {}).get("status")
    if pin_status in {"published", "publishing", "unknown"}:
        handler = f"window.location.href='/app/pinterest?post={post.id}'"
        status = ("Pinterest sandbox test" if flags["pinterest_publication"].get("sandbox") else "Published to Pinterest") if pin_status == "published" else "Check Pinterest outcome"
    action = "Continue editing" if post.status in {"draft", "drafted", "ready"} else "View post"
    if pin_status in {"published", "publishing", "unknown"}:
        action = "View Pinterest result"
    page_label = f" · {len(pages)} {'page' if len(pages) == 1 else 'pages'}" if pages else ""
    category = 'attention' if pin_status in {'unknown','publishing'} or post.status in {'failed','needs_review','publish_unknown','publish_partial','publishing'} else 'published' if pin_status == 'published' or post.status in {'published','shared'} else 'scheduled' if post.status == 'scheduled' else 'draft' if post.status in {'draft','drafted','ready'} else 'attention'
    platforms = ('<img src="/static/icons/pinterest.svg" alt="Pinterest">' if pin_status else '')
    if getattr(post, 'ig_account_id', None):
        platforms += '<img src="/static/icons/instagram.svg" alt="Instagram">'
    search_text = ' '.join([post.source_reference or '', post.topic or '', title]).lower()
    return f'''<button type="button" class="cw-post" data-post-category="{category}" data-post-search="{escape(search_text)}" onclick="{handler}">
        <span class="cw-post-image">{image}</span><span class="cw-post-copy"><span class="cw-status">{status} · {format_label}{page_label}<span class="cw-post-platforms">{platforms}</span></span>
        <strong>{escape(title)}</strong><span>{escape((post.caption or 'Source and caption stay separate.')[:110])}</span><b>{action} →</b></span></button>'''


def render_creator_workspace(user, org, posts, account, view="home", accounts=()):
    brand = org.brand_kit or {}
    signature = brand.get("signature") or "Add your signature"
    palette = PALETTES.get(brand.get("palette"), PALETTES["olive"])
    swatches = "".join(f'<i style="background:rgb{palette[key]}"></i>' for key in ("ink", "accent", "paper"))
    account_name = "@" + account.username if account and account.username else "No Instagram account connected"
    draft_posts = [p for p in posts if p.status in {"draft", "drafted", "ready"} and (p.flags or {}).get("pinterest_publication", {}).get("status") not in {"published", "publishing", "unknown"}]
    attention = [p for p in posts if p.status in {"failed", "needs_review", "publish_unknown", "publish_partial", "publishing"} or (p.flags or {}).get("pinterest_publication", {}).get("status") in {"publishing", "unknown"}]
    header = f'<header class="cw-heading"><p class="cw-eyebrow">Your creative space</p><h1>Make something meaningful.</h1></header>'
    recovery = '''<div id="creatorRecovery" class="cw-recovery hidden"><div><strong>Pick up where you left off</strong><p id="creatorRecoverySummary">Unfinished work on this device</p></div><button type="button" onclick="resumeCreatorRecovery()">Continue →</button></div>'''
    if view == "posts":
        header = '<header class="cw-heading"><p class="cw-eyebrow">Your work</p><h1>Posts</h1><p>Open a draft, review a sequence, or check a publication.</p></header>'
        body = recovery + '<div class="cw-post-tools"><label class="cw-post-search">Find a post<input id="workspacePostSearch" type="search" placeholder="Search by source or topic"></label><div class="cw-post-filters" role="group" aria-label="Post status">' + ''.join(f'<button type="button" data-post-filter="{key}" aria-pressed="{str(key == "all").lower()}">{label}</button>' for key,label in [('all','All'),('draft','Drafts'),('scheduled','Scheduled'),('published','Published'),('attention','Needs attention')]) + '</div></div><div class="cw-post-list cw-post-gallery">'  + ''.join(post_card(p) for p in posts) + '</div>'
        if not posts:
            body += '<div class="cw-empty"><h2>Your first post starts with an idea.</h2><p>Once saved, drafts will appear here.</p><button type="button" class="cw-primary" onclick="openNewPostModal()">Create a post</button></div>'
        body += '<p id="workspacePostEmpty" class="cw-empty" hidden>No posts match this view. Try another filter or source.</p><p class="cw-note">Showing the most recent 30 posts in your workspace.</p>'
    elif view == "you":
        header = '<header class="cw-heading"><p class="cw-eyebrow">Your workspace</p><h1>Make it yours.</h1><p>Your brand, account and creative tools.</p></header>'
        account_choice = ''
        if len(accounts) > 1:
            options = ''.join(f'<option value="{a.id}" {"selected" if account and a.id == account.id else ""}>@{escape(a.username or a.name)}</option>' for a in accounts)
            account_choice = f'<label class="cw-account-choice">Active Instagram account<select onchange="setActiveAccount(this.value)">{options}</select></label>'
        body = f'''<section class="cw-brand-overview"><span class="cw-brand-monogram" aria-hidden="true">{escape(org.name[:1].upper())}</span><div><h2>{escape(org.name)}</h2><p>Your voice. Your visual identity.</p></div></section><section class="cw-panel cw-connection-panel"><img src="/static/icons/instagram.svg" alt="" width="26" height="26"><h2>Instagram</h2><p>{escape(account_name)}</p>{account_choice}<a class="cw-secondary" href="/auth/instagram/login">Connect Instagram</a></section>
        <section class="cw-panel cw-connection-panel"><img src="/static/icons/pinterest.svg" alt="" width="26" height="26"><h2>Pinterest</h2><p>Prepare a Pin, connect your account and review before publishing.</p><a class="cw-secondary" href="/app/pinterest">Open Pinterest →</a></section>
        <section class="cw-panel cw-brand-panel"><span class="cw-swatches" aria-hidden="true">{swatches}</span><h2>Your brand</h2><p id="workspaceBrandSummary">{escape(signature)} · {escape(brand.get('series_name') or 'Your next series')}</p><button type="button" class="cw-primary" onclick="openCreatorBrand()">Edit brand kit</button></section>
        <details class="cw-panel" id="creatorUsage"><summary>Preview generation allowance</summary><p id="creatorUsageStatus" role="status">Open to check today's allowance.</p><p class="cw-note">Shared across this workspace and its automations. Provider attempts count even if they fail; layout edits using a saved photograph do not use image allowance.</p></details>
        <div class="cw-link-list"><a href="/app/automations">Reminder streams <span>Recurring creation and schedules →</span></a><a href="/app/library">Source library <span>Browse your knowledge library →</span></a><a href="/app/media">Visual library <span>Manage your images →</span></a></div>
        <section class="cw-panel"><h2>Help shape Sabeel</h2><p>Tell us what worked and what got in your way.</p><a class="cw-secondary" href="/app/feedback">Share feedback</a></section>
        <button type="button" class="cw-secondary" onclick="logout()">Sign out</button>'''
    else:
        body = f'''<section class="cw-create cw-create-visual"><div class="cw-create-art" aria-hidden="true"><img src="/static/img/styles/desert_glow.jpg" alt=""><img src="/static/img/styles/midnight_oasis.jpg" alt=""></div><p class="cw-eyebrow">Create with Sabeel</p><h2>Start with<br>an idea.</h2><p>Find a trusted source.<br>Make the design your own.</p>
        <button class="cw-idea" type="button" onclick="openNewPostModal()"><span>A reminder about…</span><b aria-hidden="true">→</b></button>
        <div class="cw-chips"><button type="button" onclick="startCreatorIdea('Finding ease during difficult days')">Finding ease</button><button type="button" onclick="startCreatorIdea('Being grateful for everyday blessings')">Everyday gratitude</button></div></section>
        {recovery}
        <button type="button" class="cw-source-shortcut" onclick="openCreatorSource()"><span class="cw-book" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 5c3-1 6-1 9 1 3-2 6-2 9-1v15c-3-1-6-1-9 1-3-2-6-2-9-1V5zm9 1v15"/></svg></span><span><strong>Choose a source</strong><small>Start with a Qur’an verse or Hadith you have in mind</small></span><b aria-hidden="true">→</b></button>
        <section><div class="cw-section-title"><h2>Continue creating</h2><a href="/app?view=posts">All posts →</a></div><div class="cw-post-list">{''.join(post_card(p) for p in draft_posts[:2]) or '<div class="cw-empty"><strong>Room for your first reminder.</strong><p>Start above. Your saved drafts will be waiting here.</p></div>'}</div></section>
        {('<section><div class="cw-section-title"><h2>Needs your attention</h2></div>'+''.join(post_card(p) for p in attention[:2])+'</section>') if attention else ''}
        <a class="cw-brand-strip" href="/app?view=you"><span class="cw-swatches" aria-hidden="true">{swatches}</span><span><strong>Your signature, every time</strong><small id="workspaceBrandSignature">{escape(signature)}</small></span><b aria-hidden="true">→</b></a>'''
    setup = ''
    if account is None and view != 'you':
        setup = '<section class="cw-recovery"><div><strong>Create now. Connect when you’re ready.</strong><p>Create, save and download your posts without connecting a social account. Connect Instagram when you want Sabeel to publish for you.</p><a class="cw-secondary" href="/app?view=you">Manage connections →</a></div></section>'
    return f'<div class="creator-workspace" data-view="{escape(view)}">{header}{setup}{body}</div>'


def mobile_plan(posts, display_times, today, tz):
    """A dated phone agenda over the existing account-scoped calendar results."""
    import calendar
    dates = ''.join(f'<button type="button" data-plan-day="{today.year:04d}-{today.month:02d}-{day:02d}" aria-pressed="false"><small>{calendar.day_abbr[today.replace(day=day).weekday()]}</small><strong>{day}</strong></button>' for day in range(1, calendar.monthrange(today.year, today.month)[1]+1))
    items = []
    for post in sorted(posts, key=lambda p: display_times.get(p.id) or today):
        when = display_times.get(post.id)
        if not when:
            continue
        upcoming = post.status == 'scheduled' and when >= today
        items.append(f'<article class="cw-plan-item" data-plan-date="{when.date().isoformat()}" data-plan-upcoming="{str(upcoming).lower()}"><p class="cw-plan-time">{escape(when.strftime("%a, %b %d · %I:%M %p"))}</p>{post_card(post)}</article>')
    return f'''<section class="cw-mobile-plan"><div class="cw-plan-title"><h2>{escape(today.strftime('%B %Y'))}</h2><span>Instagram schedule</span></div><div class="cw-plan-days" role="group" aria-label="Choose a day"><button type="button" data-plan-day="upcoming" aria-pressed="true">Up next</button>{dates}</div><div class="cw-plan-items">{''.join(items)}</div><div id="workspacePlanEmpty" class="cw-plan-empty" hidden><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 2v6m10-6v6M3 11h18m-10 4h4"/></svg><h3>Make room for a reminder.</h3><p>No scheduled posts in this view. Create a post, review it, then choose a time to share.</p><button type="button" class="cw-primary" onclick="openNewPostModal()">Create a post</button></div><p class="cw-note">Times shown in {escape(tz)} · this month</p></section>'''
