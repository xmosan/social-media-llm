# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from app.config import settings
from app.logging_setup import log_event

GRAPH_URL = "https://graph.facebook.com/v18.0"

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
            "pages_show_list"
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

    async def discover_ig_business_account(self, user_token: str) -> List[Dict]:
        """
        Fetches the user's FB Pages and identifies all linked Instagram Business accounts.
        Returns a detailed list of account options.
        """
        log_event("ig_discovery_start", token_present=bool(user_token))
        logger.info(f"DISCOVERY: Starting exhaustive IG account discovery for token ending in ...{user_token[-5:]}")
        
        # Step 1: Fetch FB Pages (me/accounts)
        pages_url = f"{GRAPH_URL}/me/accounts"
        # We need to request the fields specifically
        params = {
            "fields": "id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}",
            "access_token": user_token
        }
        
        discovered_accounts = []
        unique_ids = set()
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(pages_url, params=params)
            pages_data = resp.json()
            
            if "data" not in pages_data:
                err = pages_data.get("error")
                log_event("ig_discovery_pages_fail", error=err)
                logger.error(f"DISCOVERY_ERROR: Failed to fetch pages: {pages_data}")
                return []
                
            logger.info(f"DISCOVERY: Found {len(pages_data['data'])} FB Pages to inspect.")
                
            for page in pages_data["data"]:
                page_id = page["id"]
                page_name = page.get("name", "Unknown Page")
                
                # Check for nested IG account (Meta Graph API often allows this projection)
                ig_acc = page.get("instagram_business_account")
                
                if ig_acc:
                    ig_id = ig_acc.get("id")
                    if ig_id and ig_id not in unique_ids:
                        unique_ids.add(ig_id)
                        logger.info(f"DISCOVERY: Found IG '@{ig_acc.get('username')}' on Page '{page_name}'")
                        discovered_accounts.append({
                            "ig_user_id": ig_id,
                            "username": ig_acc.get("username"),
                            "name": ig_acc.get("name") or ig_acc.get("username"),
                            "profile_picture_url": ig_acc.get("profile_picture_url"),
                            "fb_page_id": page_id
                        })
                else:
                    # Fallback recursive check if nested fails
                    logger.info(f"DISCOVERY: No nested IG on '{page_name}', performing deep check...")
                    ig_url = f"{GRAPH_URL}/{page_id}"
                    ig_params = {
                        "fields": "instagram_business_account{id,username,name,profile_picture_url}",
                        "access_token": user_token
                    }
                    try:
                        ig_resp = await client.get(ig_url, params=ig_params)
                        deep_data = ig_resp.json()
                        deep_ig = deep_data.get("instagram_business_account")
                        if deep_ig:
                            ig_id = deep_ig.get("id")
                            if ig_id and ig_id not in unique_ids:
                                unique_ids.add(ig_id)
                                logger.info(f"DISCOVERY_DEEP: Found IG '@{deep_ig.get('username')}'")
                                discovered_accounts.append({
                                    "ig_user_id": ig_id,
                                    "username": deep_ig.get("username"),
                                    "name": deep_ig.get("name") or deep_ig.get("username"),
                                    "profile_picture_url": deep_ig.get("profile_picture_url"),
                                    "fb_page_id": page_id
                                })
                    except Exception as e:
                        logger.error(f"DISCOVERY_DEEP_FAIL: Error checking Page {page_id}: {e}")

        logger.info(f"DISCOVERY_COMPLETE: Total unique IG accounts: {len(discovered_accounts)}")
        return discovered_accounts

instagram_auth_service = InstagramAuthService()
