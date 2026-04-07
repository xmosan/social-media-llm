# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from app.config import settings
from app.logging_setup import log_event

GRAPH_URL = "https://graph.facebook.com/v24.0"

class InstagramAuthService:
    def __init__(self):
        self.client_id = settings.fb_app_id
        self.client_secret = settings.fb_app_secret
        # Dynamic Resolution: Prefer explicit META_REDIRECT_URI, fallback to Base URL + /auth/instagram/callback
        self.redirect_uri = settings.fb_redirect_uri or f"{settings.public_base_url.rstrip('/')}/auth/instagram/callback"

    def get_auth_url(self) -> str:
        """Construct the Meta OAuth authorization URL."""
        log_event("ig_auth_url_gen", redirect_uri=self.redirect_uri)
        print(f"DEBUG: Resolving Meta Redirect URI: {self.redirect_uri}")
        scopes = [
            "instagram_basic",
            "instagram_content_publish",
            "pages_show_list",
            "public_profile"
        ]
        scope_str = ",".join(scopes)
        return (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scope_str}"
            f"&response_type=code"
        )

    async def exchange_code_for_token(self, code: str) -> Optional[str]:
        """Exchange the authorization code for a short-lived user access token."""
        url = f"{GRAPH_URL}/oauth/access_token"
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "client_secret": self.client_secret,
            "code": code,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            log_event("ig_token_exchange_fail", error=data.get("error"))
            return None

    async def get_long_lived_token(self, short_token: str) -> Optional[Dict]:
        """Exchange short-lived token for a 60-day long-lived token."""
        url = f"{GRAPH_URL}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "fb_exchange_token": short_token,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if "access_token" in data:
                # Meta long-lived tokens typically last 60 days
                expires_in = data.get("expires_in", 5184000) # Default to 60 days
                return {
                    "access_token": data["access_token"],
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                }
            log_event("ig_long_lived_token_fail", error=data.get("error"))
            return None

    async def discover_ig_business_account(self, user_token: str) -> Optional[Dict]:
        """
        Fetches the user's FB Pages and identifies the linked Instagram Business account.
        Returns details of the first valid Instagram Business account found.
        """
        # Step 1: Fetch FB Pages
        pages_url = f"{GRAPH_URL}/me/accounts"
        params = {"access_token": user_token}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(pages_url, params=params)
            pages_data = resp.json()
            
            if "data" not in pages_data:
                log_event("ig_discovery_pages_fail", error=pages_data.get("error"))
                return None
                
            for page in pages_data["data"]:
                page_id = page["id"]
                # Step 2: Check for linked IG Business account
                ig_url = f"{GRAPH_URL}/{page_id}"
                ig_params = {
                    "fields": "instagram_business_account{id,username,name}",
                    "access_token": user_token
                }
                ig_resp = await client.get(ig_url, params=ig_params)
                ig_data = ig_resp.json()
                
                if "instagram_business_account" in ig_data:
                    ig_acc = ig_data["instagram_business_account"]
                    return {
                        "ig_user_id": ig_acc["id"],
                        "username": ig_acc.get("username"),
                        "name": ig_acc.get("name"),
                        "fb_page_id": page_id
                    }
                    
        return None

instagram_auth_service = InstagramAuthService()
