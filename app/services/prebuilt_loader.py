import os
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def load_prebuilt_packs() -> List[Dict[str, Any]]:
    """
    Load prebuilt pack JSON files from app/prebuilt_packs/
    Returns a list of pack objects.
    """
    packs = []
    # Use absolute path based on this file's location
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    packs_dir = os.path.join(base_dir, "prebuilt_packs")
    
    if not os.path.exists(packs_dir):
        logger.warning(f"Prebuilt packs directory not found: {packs_dir}")
        return []
    
    for filename in os.listdir(packs_dir):
        if filename.endswith(".json"):
            path = os.path.join(packs_dir, filename)
            try:
                with open(path, 'r') as f:
                    pack = json.load(f)
                    packs.append(pack)
            except Exception as e:
                logger.error(f"Failed to load prebuilt pack {filename}: {e}")
                
    return packs
