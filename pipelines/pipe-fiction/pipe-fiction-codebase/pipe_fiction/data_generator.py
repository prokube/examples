"""
Simple DataGenerator for demonstrating KFP debugging.
"""

from loguru import logger
from typing import List


class DataGenerator:
    """Simple text data generator for debugging demos."""
    
    def __init__(self):
        logger.info("📝 Initializing DataGenerator")
    
    def create_sample_data(self) -> List[str]:
        """Create sample text lines for processing."""
        logger.info("🔧 Creating sample text data")
        
        lines = [
            "Here are some random useless lines of text.",
            "Line 1: MLOps is an important topic.",
            "Line 2: Kubeflow Pipeline are hard to debug, sometimes.",
            "Line 3: prokube.ai seems to be a nice company."
        ]
        
        logger.success(f"✅ Created {len(lines)} sample lines")
        return lines
