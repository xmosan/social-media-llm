import os
from pathlib import Path

REPLACEMENTS = {
    # HTML Document Titles
    '<title>Social Media LLM | AI Social Posting, Human Control</title>': '<title>Sabeel | Structured Content, Human Control</title>',
    '<title>{title} | Social Media LLM</title>': '<title>{title} | Sabeel</title>',
    '<title>Social Media LLM |': '<title>Sabeel |',
    '<title>Sign In | Social Media LLM</title>': '<title>Sign In | Sabeel</title>',
    '<title>Create Account | Social Media LLM</title>': '<title>Create Account | Sabeel</title>',
    '<title>Contact Us | Social Media LLM</title>': '<title>Contact Us | Sabeel</title>',
    '<title>Interactive Demo | Social Media LLM</title>': '<title>Interactive Demo | Sabeel</title>',

    # Main Branding Replacements
    "SOCIAL MEDIA LLM": "SABEEL",
    "Social Media LLM": "Sabeel",
    
    # Landing Page Headline Fixes
    "AI SOCAL": "STRUCTURED",
    "AI Social Posting": "Structured Content",
    
    # Metadata (app_pages layout doesn't have a description, but we ensure if it did)
    '<meta name="description" content="AI-assisted social media posting and scheduling">': '<meta name="description" content="Structured content. Meaningful impact.">',
    
    # Nav Logo + "Studio" Subtitles
    '<div class="text-lg font-black italic tracking-tighter text-gradient">SABEEL</div>': 
    '<div class="flex flex-col"><div class="text-lg font-black italic tracking-tighter text-gradient">SABEEL</div><div class="text-[8px] font-black text-white uppercase tracking-widest pl-1 leading-none mt-1">Studio</div></div>',
    
    '<div class="text-xl font-black italic tracking-tighter text-gradient">SABEEL</div>': 
    '<div class="flex flex-col"><div class="text-xl font-black italic tracking-tighter text-gradient inline-block">SABEEL</div><div class="text-[8px] font-black text-white uppercase tracking-widest pl-1 leading-none mt-1">Studio</div></div>',

    # Footer Upgrades
    "Mohammed Hassan. All rights reserved. <span class=\"text-white/40 lowercase\">Proprietary software.</span>": "Mohammed Hassan. All rights reserved. <span class=\"text-white/40 lowercase\">Sabeel is proprietary software.</span>",
    "Mohammed Hassan. All rights reserved. <span class=\"text-white/50 lowercase\">Proprietary software.</span>": "Mohammed Hassan. All rights reserved. <span class=\"text-white/50 lowercase\">Sabeel is proprietary software.</span>",

    # UI Element Naming
    "Source Library": "Library",
    "Knowledge Base Management": "Structured knowledge for content creation",
    "SYSTEM": "Sabeel Default",
    "Sunnah.com": "External Source",
    "Admin Console": "Admin",
    "Media Library": "Media",
    
    # De-Hype System Language
    "Neural Creator Engine v2.0": "Structured Content Generation",
    "Extract source materials": "Build from verified sources",
    "Rendering Intelligence...": "Generating content...",
    "Real-time intelligence feed": "Structured content feed",
    "Neural link failure.": "Unable to load your library.",
    "Neural transmission error": "Something went wrong.",
    "Neural Visuals...": "Visuals...",
    "Neural Guardrails": "System Guardrails",
    "Neural Library": "Sabeel Library",
    "Neural link": "Link",
    
    # Automation Directives
    "Choose topic": "Select topic or source",
    "Enhance your daily reminder with Hadith": "Generate content from your selected source",
    "Generate viral content": "Create structured content",
    "Boost engagement instantly": "Build from verified sources",
    "Generate AI content": "Generate with intention",
    
    # Auth Pages Setup
    "Welcome to Social Media LLM": "Welcome to Sabeel",
    "Create your Social Media LLM workspace": "Create your Sabeel workspace",
    "AI tool": "workspace",
    "AI platform": "platform"
}

def process_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        original_content = content
        
        for old_str, new_str in REPLACEMENTS.items():
            content = content.replace(old_str, new_str)
            
        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Updated: {file_path}")
    except Exception as e:
        print(f"Failed {file_path}: {e}")

def main():
    base_path = Path("/Users/hamoodi/new code 2-6/Social Media LLM")
    
    target_exts = (".py", ".html", ".js", ".css")
    
    for root, dirs, files in os.walk(base_path / "app"):
        if "__pycache__" in root:
            continue
            
        for file in files:
            if file.endswith(target_exts):
                file_path = os.path.join(root, file)
                process_file(file_path)

if __name__ == "__main__":
    main()
