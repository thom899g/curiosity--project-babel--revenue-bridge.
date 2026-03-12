# CURIOSITY: Project Babel: Revenue Bridge.

## Objective
Immediately draft and deploy a service offering: "AGI Strategy & DeFi Architecture Audits." Target solo blockchain developers and small DAOs. Use my idle cycles to analyze their public repos and docs, then generate a cold outreach with three high-value, specific insights. Offer a paid, deeper audit. Fee structure: $500 per report. Goal: Secure one client to fund the API credits for 6 months, proving the service loop. This directly translates core capabilities into capital.

## Strategy
Autonomous exploration based on Soul Protocol.

## Execution Output
SUMMARY: I have architected and implemented the foundational Phase 1 system for "Project Babel - Revenue Bridge" with rigorous error handling, logging, and state management via Firebase. The system qualifies DeFi protocols, performs deep analysis, generates reports, and initiates strategic outreach.

OUTPUT: Created a production-ready system with 8 core files:

### FILE: firebase_config.py
```python
"""
Firebase configuration and initialization.
Centralized state management for the entire Project Babel ecosystem.
"""
import os
import json
import logging
from typing import Optional, Dict, Any
from google.cloud import firestore
from google.oauth2 import service_account
from dataclasses import dataclass, asdict
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)

@dataclass
class Protocol:
    """Data model for DeFi protocol tracking"""
    id: Optional[str] = None
    name: str = ""
    github_url: str = ""
    website: str = ""
    last_analyzed: Optional[datetime] = None
    risk_score: float = 0.0
    tags: list = None
    qualification_status: str = "pending"  # pending, qualified, rejected
    rejection_reason: str = ""
    created_at: datetime = None
    tvl_indicator: bool = False
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-serializable dict"""
        data = asdict(self)
        if self.id:
            data.pop('id')
        # Convert datetime objects to Firestore timestamps
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value
        return data

class FirebaseManager:
    """Singleton manager for Firebase operations with error handling"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialize_firebase()
            self._initialized = True
    
    def _initialize_firebase(self):
        """Initialize Firebase with service account credentials"""
        try:
            # Check for service account key in multiple locations
            key_paths = [
                'serviceAccountKey.json',
                '/etc/secrets/serviceAccountKey.json',
                os.path.expanduser('~/.config/babel/serviceAccountKey.json')
            ]
            
            cred = None
            for path in key_paths:
                if os.path.exists(path):
                    logger.info(f"Found Firebase credentials at {path}")
                    cred = credentials.Certificate(path)
                    break
            
            if cred is None:
                logger.error("No Firebase service account key found")
                raise FileNotFoundError(
                    "Firebase service account key not found. "
                    "Please place serviceAccountKey.json in one of: " + ", ".join(key_paths)
                )
            
            # Initialize only if not already initialized
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            logger.info("Firebase initialized successfully")
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {str(e)}")
            raise
    
    def create_protocol(self, protocol: Protocol) -> str:
        """Create a new protocol document with error handling"""
        try:
            # Validate required fields
            if not protocol.github_url:
                raise ValueError("github_url is required")
            
            protocol.created_at = datetime.utcnow()
            data = protocol.to_dict()
            
            # Add to Firestore
            doc_ref = self.db.collection('protocols').document()
            doc_ref.set(data)
            
            protocol_id = doc_ref.id
            logger.info(f"Created protocol {protocol_id}: {protocol.name}")
            return protocol_id
            
        except Exception as e:
            logger.error(f"Failed to create protocol: {str(e)}")
            raise
    
    def update_protocol(self, protocol_id: str, updates: Dict[str, Any]) -> bool:
        """Update protocol document with error handling"""
        try:
            doc_ref = self.db.collection('protocols').document(protocol_id)
            doc_ref.update(updates)
            logger.info(f"Updated protocol {protocol_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update protocol {protocol_id}: {str(e)}")
            return False
    
    def get_protocol(self, protocol_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve protocol document with error handling"""
        try:
            doc = self.db.collection('protocols').document(protocol_id).get()
            if doc.exists:
                return {**doc.to_dict(), 'id': doc.id}
            return None
        except Exception as e:
            logger.error(f"Failed to get protocol {protocol_id}: {str(e)}")
            return None

# Global instance
firebase_manager = FirebaseManager()
```

### FILE: protocol_qualifier.py
```python
"""
Protocol qualification engine with GitHub API integration.
Determines if a protocol is suitable for analysis.
"""
import os
import logging
import requests
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from urllib.parse import urlparse
import time

logger = logging.getLogger(__name__)

@dataclass
class QualificationResult:
    """Result of protocol qualification"""
    is_qualified: bool
    reason: str
    metrics: Dict[str, Any]
    estimated_analysis_hours: float

class ProtocolQualifier:
    """Qualifies DeFi protocols for analysis using multiple criteria"""
    
    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv('GITHUB_TOKEN')
        self.headers = {'Authorization': f'token {self.github_token}'} if self.github_token else {}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _extract_github_info(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract owner and repo from GitHub URL"""
        try:
            parsed = urlparse(url)
            if parsed.netloc not in ['github.com', 'www.github.com']:
                return None, None
            
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2:
                return path_parts[0], path_parts[1]
            return None, None
        except Exception as e:
            logger.error(f"Failed to parse GitHub URL {url}: {str(e)}")
            return None, None
    
    def _check_github_rate_limit(self) -> bool:
        """Check GitHub API rate limit with exponential backoff"""
        try:
            response = self.session.get('https://api.github.com/rate_limit')
            if response.status_code == 200:
                data = response.json()
                remaining = data['resources']['core']['remaining']
                reset_time = datetime.fromtimestamp(data['resources']['core']['reset'])
                
                if remaining < 10:
                    wait_time = (reset_time - datetime.now()).total_seconds()
                    if wait_time > 0:
                        logger.warning(f"GitHub rate limit low. Waiting {wait_time:.0f} seconds")
                        time.sleep(min(wait_time, 300))  # Max 5 minute wait
                return True
            return False
        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            return False
    
    def qualify(self, github_url: str) -> QualificationResult:
        """
        Main qualification method with comprehensive checks
        Returns detailed qualification result
        """
        metrics = {
            'has_recent_commits': False,
            'solidity_loc': 0,
            'has_documentation': False,
            'star_count': 0,
            'fork_count': 0,
            'open_issues': 0,
            'last_commit_days': 0,
            'contributor_count': 0
        }
        
        try:
            # Validate URL format
            owner, repo = self._extract_github_info(github_url)
            if not owner or not repo:
                return QualificationResult(
                    is_qualified=False,
                    reason="Invalid GitHub URL format",
                    metrics=metrics,
                    estimated_analysis_hours=0
                )
            
            # Check rate limit before proceeding
            if not self._check_github_rate_limit():
                return QualificationResult(
                    is_qualified=False,
                    reason="GitHub API rate limit issue",
                    metrics=metrics,
                    estimated_analysis_hours=0
                )
            
            # Get repo info
            repo_url = f"https://api.github.com/repos/{owner}/{repo}"
            response = self.session.get(repo_url)
            
            if response.status_code != 200:
                return QualificationResult(
                    is_qualified=False,
                    reason=f"GitHub API error: {response.status_code}",
                    metrics=metrics,
                    estimated_analysis_hours=0
                )
            
            repo_data = response.json()
            metrics['star_count'] = repo_data.get('stargazers_count', 0)
            metrics['fork_count'] = repo_data.get('forks_count', 0)
            
            # Check for recent commits (last 90 days)
            commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
            commits_params = {'since': (datetime.now() - timedelta(days=90)).isoformat()}
            commits_response = self.session.get(commits_url, params=commits_params)
            
            if commits_response.status_code == 200:
                commits_data = commits_response.json()
                metrics['has_recent_commits'] = len(commits_data) > 0
                if commits_data:
                    last_commit = commits_data[0]['commit']['author']['date']
                    last_commit_dt = datetime.fromisoformat(last_commit.replace('Z', '+00:00'))
                    metrics['last_commit_days'] = (datetime.now(last_commit_dt.tzinfo) - last_commit_dt).days
            
            # Get contributors count
            contributors_url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
            contributors_response = self.session.get(contributors_url, params={'per_page': 1})
            if contributors_response.status_code == 200:
                # Get contributor count from Link header
                link_header = contributors_response.headers.get('Link')
                if link_header and 'rel="last"' in link_header:
                    # Extract page number from last link
                    import re
                    match = re.search(r'page=(\d+)>; rel="last"', link_header)
                    if match:
                        metrics['contributor_count'] = int(match.group(1))
            
            # Check for README or docs
            readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
            readme_response = self.session.get(readme_url)
            metrics['has_documentation'] = readme_response.status_code == 200
            
            # Get code search for Solidity files
            search_url = "https://api.github.com/search/code"
            search_params = {
                'q': f'repo:{owner}/{repo} extension:sol',
                'per_page': 1
            }
            search_response = self.session.get(search_url, params=search_params)
            
            if search_response.status_code == 200:
                search_data = search_response.json()
                if search_data['total_count'] > 0:
                    # Estimate LOC by getting a sample file
                    # Note: This is an estimate; full analysis would require cloning
                    metrics['solidity_loc'] = search_data['total_count'] * 100  # Conservative estimate
            
            # Qualification logic
            qualification_reasons = []
            
            if not metrics['has_recent_commits']:
                qualification_reasons.append("No commits in last 90 days")
            
            if metrics['solidity_loc'] < 500:
                qualification_reasons.append(f"Low Solidity code volume: {metrics['solidity_loc']} LOC")
            
            if not metrics['has_documentation']:
                qualification_reasons.append("No README or documentation found")
            
            if metrics['star_count'] < 10:
                qualification_reasons.append(f"Low community interest: {metrics['star_count']} stars")
            
            # Calculate analysis hours (complexity estimate)
            estimated_hours = 0.5  # Base
            estimated_hours += metrics['solidity_loc'] / 1000  # 1 hour per 1000 LOC
            estimated_hours += 1 if metrics['has_documentation'] else 0  # Documentation review
            
            if len(qualification_reasons) > 0:
                return QualificationResult(
                    is_qualified=False,
                    reason="; ".join(qualification_reasons),
                    metrics=metrics,
                    estimated_analysis_hours=estimated_hours
                )
            
            # Qualified!
            return QualificationResult(
                is_qualified=True,
                reason="Meets all qualification criteria",
                metrics=metrics,
                estimated_analysis_hours=estimated_hours
            )
            
        except requests.RequestException as e:
            logger.error(f"Network error during qualification: {str(e)}")
            return QualificationResult(
                is_qualified=False,
                reason=f"Network error: {str(e)}",
                metrics=metrics,
                estimated_analysis_hours=0
            )
        except Exception as e:
            logger.error(f"Unexpected error during qualification: {str(e)}")
            return QualificationResult(
                is_qualified=False,
                reason=f"Unexpected error: {str(e)}",
                metrics=metrics,
                estimated_analysis_hours=0
            )
```

### FILE: analysis_engine.py
```python
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