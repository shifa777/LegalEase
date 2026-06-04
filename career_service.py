"""
Career Service for LegalEase
Provides legal job search using Jooble REST API
"""

import os
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class CareerService:
    def __init__(self):
        """Initialize the Career service with Jooble API"""
        # Prefer environment variable, but allow provided key fallback for convenience
        self.jooble_api_key = os.getenv('JOOBLE_API_KEY') or '775ef7a0-ac6e-4a14-976e-6ef3d4044405'
        self.base_url = f"https://jooble.org/api/{self.jooble_api_key}"
        # Simple in-memory cache with TTL (seconds)
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl_seconds: int = int(os.getenv('CAREER_CACHE_TTL', '120'))
        
    def search_lawyer_jobs(self, location: str = "India", rows: int = 50) -> Dict:
        """Search for lawyer jobs using Jooble.

        Args:
            location: Job location (default: "India")
            rows: Approximate number of jobs to fetch.

        Returns:
            Dict with success status and job data
        """
        try:
            cache_key = f"jooble|lawyer|{location}|{rows}"
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached

            # Jooble API expects POST with JSON body
            payload = {
                "keywords": "lawyer OR attorney OR legal OR counsel",
                "location": location,
                # Jooble returns 20 per page typically; iterate pages until >= rows or page cap
                "page": 1,
            }

            jobs: List[Dict] = []
            page = 1
            page_cap = max(1, min(10, (rows // 20) + 1))
            headers = {"Content-Type": "application/json"}
            while len(jobs) < rows and page <= page_cap:
                payload["page"] = page
                resp = requests.post(self.base_url, json=payload, headers=headers, timeout=20)
                if resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Jooble HTTP {resp.status_code}: {resp.text[:200]}",
                        "jobs": [],
                        "total": 0,
                    }
                data = resp.json() or {}
                items = data.get("jobs") or data.get("results") or []
                if not items:
                    break
                jobs.extend(items)
                page += 1

            formatted = self._format_jooble_jobs(jobs[:rows])
            result = {
                "success": True,
                "jobs": formatted,
                "total": len(formatted),
                "timestamp": datetime.now().isoformat(),
            }
            self._set_cache(cache_key, result)
            return result
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Network error: {e}", "jobs": [], "total": 0}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}", "jobs": [], "total": 0}
    
    def _format_jooble_jobs(self, jobs: List[Dict]) -> List[Dict]:
        formatted: List[Dict] = []
        for j in jobs:
            # Jooble typical fields
            # { id?, title, location, company, salary, snippet, link, updated, type }
            formatted.append({
                "id": j.get("id") or j.get("jobid") or j.get("link"),
                "title": j.get("title"),
                "company": j.get("company") or j.get("companyName"),
                "location": j.get("location"),
                "salary": j.get("salary"),
                "description": (j.get("snippet") or j.get("description") or "")[:500],
                "job_url": j.get("link"),
                "company_url": None,
                "posted_time": j.get("updated") or j.get("date"),
                "applications_count": None,
                "contract_type": j.get("type"),
                "experience_level": None,
                "work_type": None,
                "sector": None,
                "apply_type": None,
                "apply_url": j.get("link"),
                "published_at": j.get("updated") or j.get("date"),
            })
        return formatted
    
    def _get_dataset_results(self, dataset_id: str) -> Dict:
        """
        Fetch results from the dataset
        
        Args:
            dataset_id: Apify dataset ID
            
        Returns:
            Dict with formatted job data
        """
        dataset_url = f"{self.base_url}/datasets/{dataset_id}/items"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        try:
            response = requests.get(dataset_url, headers=headers, timeout=30)
            response.raise_for_status()
            jobs = response.json()
            
            # Filter and format lawyer-specific jobs
            lawyer_jobs = self._filter_lawyer_jobs(jobs)
            
            return {
                "success": True,
                "jobs": lawyer_jobs,
                "total": len(lawyer_jobs),
                "timestamp": datetime.now().isoformat()
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to fetch dataset results: {str(e)}",
                "jobs": [],
                "total": 0
            }
    
    def _filter_lawyer_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """
        Filter jobs to include only lawyer/legal positions
        
        Args:
            jobs: Raw job data from Apify
            
        Returns:
            List of filtered and formatted job data
        """
        lawyer_keywords = [
            "lawyer", "attorney", "legal", "counsel", "paralegal", 
            "litigation", "corporate law", "criminal law", "family law",
            "immigration law", "real estate law", "intellectual property",
            "compliance", "legal assistant", "legal secretary", "judge",
            "court", "advocate", "barrister", "solicitor"
        ]
        
        filtered_jobs = []
        
        for job in jobs:
            title = job.get("title", "").lower()
            description = job.get("description", "").lower()
            work_type = job.get("workType", "").lower()
            
            # Check if job title or description contains lawyer keywords
            if any(keyword in title or keyword in description or keyword in work_type 
                   for keyword in lawyer_keywords):
                # Format the job data
                formatted_job = {
                    "id": job.get("id"),
                    "title": job.get("title"),
                    "company": job.get("companyName"),
                    "location": job.get("location"),
                    "salary": job.get("salary"),
                    "description": job.get("description", "")[:500] + "..." if len(job.get("description", "")) > 500 else job.get("description", ""),
                    "job_url": job.get("jobUrl"),
                    "company_url": job.get("companyUrl"),
                    "posted_time": job.get("postedTime"),
                    "applications_count": job.get("applicationsCount"),
                    "contract_type": job.get("contractType"),
                    "experience_level": job.get("experienceLevel"),
                    "work_type": job.get("workType"),
                    "sector": job.get("sector"),
                    "apply_type": job.get("applyType"),
                    "apply_url": job.get("applyUrl"),
                    "published_at": job.get("publishedAt")
                }
                filtered_jobs.append(formatted_job)
        
        return filtered_jobs
    
    def search_jobs_with_keywords(
        self, 
        location: str = "India", 
        keywords: str = "", 
        rows: int = 50
    ) -> Dict:
        """
        Search jobs with additional keyword filtering
        
        Args:
            location: Job location
            keywords: Additional search keywords (comma-separated)
            rows: Number of jobs to fetch
            
        Returns:
            Dict with filtered job results
        """
        # Cache per keyword set as well
        base_key = f"lawyer_jobs_kw|{location}|{min(rows, 100)}|{keywords.strip().lower()}"
        cached = self._get_cache(base_key)
        if cached is not None:
            return cached

        # First get all jobs from Jooble using base lawyer keywords
        result = self.search_lawyer_jobs(location=location, rows=rows)
        
        if not result.get("success") or not keywords:
            return result
        
        # Filter by additional keywords if provided
        keyword_list = [kw.strip().lower() for kw in keywords.split(',')]
        filtered_jobs = []
        
        for job in result.get("jobs", []):
            job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('work_type', '')}".lower()
            if any(keyword in job_text for keyword in keyword_list):
                filtered_jobs.append(job)
        
        result["jobs"] = filtered_jobs
        result["total"] = len(filtered_jobs)
        result["keywords"] = keywords
        
        # Put into cache
        self._set_cache(base_key, result)
        return result

    def _get_cache(self, key: str) -> Optional[Dict]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts = entry.get("_ts")
        if not ts:
            return None
        if (datetime.now().timestamp() - ts) <= self._cache_ttl_seconds:
            return {k: v for k, v in entry.items() if k != "_ts"}
        # Expired
        self._cache.pop(key, None)
        return None

    def _set_cache(self, key: str, value: Dict) -> None:
        self._cache[key] = {**value, "_ts": datetime.now().timestamp()}

# Create a singleton instance
career_service = CareerService()

