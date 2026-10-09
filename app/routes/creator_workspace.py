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
    action = "Continue editing" if post.status in {"draft", "drafted", "ready"} else "View post"
    page_label = f" · {len(pages)} {'page' if len(pages) == 1 else 'pages'}" if pages else ""
    return f'''<button type="button" class="cw-post" onclick="{handler}">
        <span class="cw-post-image">{image}</span><span class="cw-post-copy"><span class="cw-status">{status} · {format_label}{page_label}</span>
        <strong>{escape(title)}</strong><span>{escape((post.caption or 'Source and caption stay separate.')[:110])}</span><b>{action} →</b></span></button>'''


def render_creator_workspace(user, org, posts, account, view="home", accounts=()):
    brand = org.brand_kit or {}
    signature = brand.get("signature") or "Add your signature"
    palette = PALETTES.get(brand.get("palette"), PALETTES["olive"])
    swatches = "".join(f'<i style="background:rgb{palette[key]}"></i>' for key in ("ink", "accent", "paper"))
    account_name = "@" + account.username if account and account.username else "No Instagram account connected"
    draft_posts = [p for p in posts if p.status in {"draft", "drafted", "ready"}]
    attention = [p for p in posts if p.status in {"failed", "needs_review", "publish_unknown", "publish_partial", "publishing"}]
    header = f'<header class="cw-heading"><p class="cw-eyebrow">Your creative space</p><h1>Make something meaningful.</h1><p>A source you trust. A post that feels like you.</p></header>'
    recovery = '''<div id="creatorRecovery" class="cw-recovery hidden"><div><strong>Pick up where you left off</strong><p id="creatorRecoverySummary">Unfinished work on this device</p></div><button type="button" onclick="resumeCreatorRecovery()">Continue →</button></div>'''
    if view == "posts":
        header = '<header class="cw-heading"><p class="cw-eyebrow">Your work</p><h1>Posts</h1><p>Open a draft, review a sequence, or check a publication.</p></header>'
        body = recovery + '<div class="cw-post-list">' + ''.join(post_card(p) for p in posts) + '</div>'
        if not posts:
            body += '<div class="cw-empty"><h2>Your first post starts with an idea.</h2><p>Once saved, drafts will appear here.</p><button type="button" class="cw-primary" onclick="openNewPostModal()">Create a post</button></div>'
        body += '<p class="cw-note">Showing the most recent 30 posts for the selected account.</p>'
    elif view == "you":
        header = '<header class="cw-heading"><p class="cw-eyebrow">Your workspace</p><h1>Make it yours.</h1><p>Your brand, account and creative tools.</p></header>'
        account_choice = ''
        if len(accounts) > 1:
            options = ''.join(f'<option value="{a.id}" {"selected" if account and a.id == account.id else ""}>@{escape(a.username or a.name)}</option>' for a in accounts)
            account_choice = f'<label class="cw-account-choice">Active Instagram account<select onchange="setActiveAccount(this.value)">{options}</select></label>'
        body = f'''<section class="cw-panel"><h2>{escape(org.name)}</h2><p>{escape(account_name)}</p>{account_choice}<a class="cw-secondary" href="/auth/instagram/login">Connect Instagram</a></section>
        <section class="cw-panel"><h2>Your brand</h2><p id="workspaceBrandSummary">{escape(signature)} · {escape(brand.get('series_name') or 'Your next series')}</p><button type="button" class="cw-primary" onclick="openCreatorBrand()">Edit brand kit</button></section>
        <details class="cw-panel" id="creatorUsage"><summary>Preview generation allowance</summary><p id="creatorUsageStatus" role="status">Open to check today's allowance.</p><p class="cw-note">Shared across this workspace and its automations. Provider attempts count even if they fail; layout edits using a saved photograph do not use image allowance.</p></details>
        <div class="cw-link-list"><a href="/app/automations">Reminder streams <span>Recurring creation and schedules →</span></a><a href="/app/library">Source library <span>Browse your knowledge library →</span></a><a href="/app/media">Visual library <span>Manage your images →</span></a></div>
        <button type="button" class="cw-secondary" onclick="logout()">Sign out</button>'''
    else:
        body = f'''{recovery}<section class="cw-create"><div class="cw-create-mark" aria-hidden="true">✦</div><p class="cw-eyebrow">Create with Sabeel</p><h2>What’s on your heart<br>to share today?</h2><p>Bring the idea. We’ll help with the preparation.<br>You make the final choices.</p>
        <button class="cw-idea" type="button" onclick="openNewPostModal()"><span>A reminder about…</span><b aria-hidden="true">→</b></button>
        <div class="cw-chips"><button type="button" onclick="startCreatorIdea('Finding ease during difficult days')">Finding ease</button><button type="button" onclick="startCreatorIdea('Being grateful for everyday blessings')">Everyday gratitude</button></div></section>
        <button type="button" class="cw-source-shortcut" onclick="openCreatorSource()"><span class="cw-book" aria-hidden="true">▤</span><span><strong>Choose a source</strong><small>Start with a Qur’an verse or Hadith you have in mind</small></span><b aria-hidden="true">→</b></button>
        <section><div class="cw-section-title"><h2>Continue creating</h2><a href="/app?view=posts">All posts →</a></div><div class="cw-post-list">{''.join(post_card(p) for p in draft_posts[:2]) or '<div class="cw-empty"><strong>Room for your first reminder.</strong><p>Start above. Your saved drafts will be waiting here.</p></div>'}</div></section>
        {('<section><div class="cw-section-title"><h2>Needs your attention</h2></div>'+''.join(post_card(p) for p in attention[:2])+'</section>') if attention else ''}
        <a class="cw-brand-strip" href="/app?view=you"><span class="cw-swatches" aria-hidden="true">{swatches}</span><span><strong>Your signature, every time</strong><small id="workspaceBrandSignature">{escape(signature)}</small></span><b aria-hidden="true">→</b></a>'''
    setup = ''
    if account is None and view != 'you':
        setup = '<section class="cw-recovery"><div><strong>Connect Instagram to save your posts</strong><p>You can explore sources and keep ideas on this device. Workspace drafts, exports and publishing need a connected account.</p><a class="cw-secondary" href="/app?view=you">Set up your account →</a></div></section>'
    return f'<div class="creator-workspace" data-view="{escape(view)}">{header}{setup}{body}</div>'
