"""
Core analysis engine with Slither integration and LLM reasoning.
Handles code cloning, static analysis, and intelligent insight generation.
"""
import os
import subprocess
import tempfile
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import shutil
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

class AnalysisEngine:
    """Orchestrates code analysis with multiple tools"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.temp_dirs = []
    
    def __del__(self):
        """Cleanup temp directories"""
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    def _clone_repository(self, github_url: str) -> Optional[Path]:
        """Clone repository to temporary directory with error handling"""
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="babel_analysis_")
            self.temp_dirs.append(temp_dir)
            
            logger.info(f"Cloning {github_url} to {temp_dir}")
            
            # Use git with timeout
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', github_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Git clone failed: {result.stderr}")
                return None
            
            return Path(temp_dir)
            
        except subprocess.TimeoutExpired:
            logger.error(f"Git clone timeout for {github_url}")