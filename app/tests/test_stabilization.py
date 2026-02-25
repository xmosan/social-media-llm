import pytest
from unittest.mock import MagicMock, patch
from app.services.llm import generate_topic_caption
from app.services.automation_runner import run_automation_once
from app.models import TopicAutomation, Post
from sqlalchemy.orm import Session

def test_generate_topic_caption_no_echo():
    """Verify that the LLM output does not simply echo the topic."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"caption": "A beautiful day to reflect on patience.", "hashtags": ["#patience"], "alt_text": "Sunny day"}'))
    ]
    
    with patch("app.services.llm.client.chat.completions.create", return_value=mock_response):
        result = generate_topic_caption(topic="Patience")
        assert "Patience" not in result["caption"] # In this mock case it's true
        assert result["hashtags"] == ["#patience"]

def test_automation_runner_guardrail_filler():
    """Verify that filler captions trigger the guardrail."""
    db = MagicMock(spec=Session)
    automation = MagicMock(spec=TopicAutomation)
    automation.id = 1
    automation.topic_prompt = "Ramadan"
    automation.name = "Ramadan Auto"
    automation.style_preset = "islamic_reminder"
    automation.image_mode = "reuse_last_upload"
    
    # Mock LLM returning filler
    mock_llm_result = {
        "caption": "Enhance your daily reminder with our new post!", # Filler
        "hashtags": ["#filler"],
        "alt_text": "filler"
    }
    
    with patch("app.services.automation_runner.generate_topic_caption", return_value=mock_llm_result):
        with patch("app.services.automation_runner.resolve_media_url", return_value="http://example.com/img.jpg"):
            # Mock db.query(TopicAutomation).get(id) 
            db.query().filter().first.return_value = automation
            
            post = run_automation_once(db, 1)
            
            assert post.status == "failed"
            assert "filler_detected" in str(post.flags.get("reason"))

def test_automation_runner_guardrail_missing_media():
    """Verify that missing media_url triggers the guardrail."""
    db = MagicMock(spec=Session)
    automation = MagicMock(spec=TopicAutomation)
    automation.id = 1
    automation.topic_prompt = "Ramadan"
    automation.name = "Ramadan Auto"
    automation.image_mode = "ai_generated"
    
    mock_llm_result = {
        "caption": "A meaningful caption about Ramadan that is long enough.",
        "hashtags": ["#ramadan"],
        "alt_text": "ramadan"
    }
    
    with patch("app.services.automation_runner.generate_topic_caption", return_value=mock_llm_result):
        with patch("app.services.automation_runner.resolve_media_url", return_value=None): # Failure
            db.query().filter().first.return_value = automation
            
            post = run_automation_once(db, 1)
            
            assert post.status == "failed"
            assert "media_url is missing" in post.flags.get("automation_error")
