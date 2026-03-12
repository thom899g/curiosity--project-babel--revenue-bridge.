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