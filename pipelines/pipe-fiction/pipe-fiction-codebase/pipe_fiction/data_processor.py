"""
Simple DataProcessor for demonstrating KFP debugging.
"""

from loguru import logger
from typing import Any, List, Dict


class DataProcessor:
    """Simple text processor with logging."""

    def __init__(self):
        logger.info("🔧 Initializing DataProcessor")

    def process_lines(self, lines: List[str]) -> List[Dict[str, object]]:
        """Process lines and extract useful information."""
        logger.info(f"⚙️  Processing {len(lines)} lines")

        processed_data = []

        for i, line in enumerate(lines, 1):
            # Clean the line
            clean_line = line.strip()

            if not clean_line:
                logger.debug(f"⏭️  Skipping empty line {i}")
                continue

            # Extract some info
            processed_item = {
                "line_number": i,
                "original": clean_line,
                "word_count": len(clean_line.split()),
                "contains_mlops": "mlops" in clean_line.lower(),
                "contains_kubeflow": "kubeflow" in clean_line.lower(),
                "length": len(clean_line),
            }

            processed_data.append(processed_item)
            logger.debug(f"✨ Processed line {i}: {processed_item['word_count']} words")

        logger.success(f"🎉 Successfully processed {len(processed_data)} lines")
        return processed_data

    def get_summary(self, processed_data: List[Dict[str, object]]) -> Dict[str, Any]:
        """Get summary statistics."""
        logger.info("📊 Generating summary statistics")

        if not processed_data:
            return {"total_lines": 0}

        summary = {
            "total_lines": len(processed_data),
            "total_words": sum(item["word_count"] for item in processed_data),
            "mlops_mentions": sum(
                1 for item in processed_data if item["contains_mlops"]
            ),
            "kubeflow_mentions": sum(
                1 for item in processed_data if item["contains_kubeflow"]
            ),
            "avg_line_length": sum(item["length"] for item in processed_data)
            / len(processed_data),
        }

        logger.info(f"📈 Summary: {summary}")
        return summary
