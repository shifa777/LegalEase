"""
News Service for LegalEase
Provides legal news from Mediastack API
"""

import os
import requests
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class NewsService:
    def __init__(self):
        """Initialize the News service with Mediastack API"""
        # No hardcoded default; use env var. If missing, we'll use mock data transparently
        self.api_key = os.getenv('MEDIASTACK_API_KEY')
        self.base_url = "http://api.mediastack.com/v1/news"
        # Simple in-memory cache with TTL
        self._cache = {}
        self._cache_ttl_seconds = int(os.getenv('NEWS_CACHE_TTL', '120'))
    
    def _get_cache(self, key: str) -> Optional[Dict]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts = entry.get('_ts')
        if ts is None:
            return None
        if (datetime.now().timestamp() - ts) <= self._cache_ttl_seconds:
            return {k: v for k, v in entry.items() if k != '_ts'}
        # Expired
        self._cache.pop(key, None)
        return None

    def _set_cache(self, key: str, value: Dict) -> None:
        self._cache[key] = {**value, '_ts': datetime.now().timestamp()}
        
    def get_news(
        self, 
        category: str = 'general',
        country: Optional[str] = None,
        language: str = 'en',
        limit: int = 25,
        keywords: Optional[str] = None
    ) -> Dict:
        """
        Get news from Mediastack API with fallback to mock data
        
        Args:
            category: News category (general, sports, business, etc.)
            country: Country code (us, gb, in, etc.)
            language: Language code (en, etc.)
            limit: Number of results (max 100)
            keywords: Optional keywords to filter news
            
        Returns:
            Dict with success status and news data
        """
        try:
            # Caching layer
            cache_key = (
                f"news|{category}|{country or ''}|{language}|{min(limit, 100)}|{keywords or ''}"
            )
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached

            # If API key missing, return mock data without attempting network
            if not self.api_key:
                print("[NEWS] No MediaStack API key. Using mock news.")
                return self._get_mock_news(category, keywords, limit)
            params = {
                'access_key': self.api_key,
                'categories': category,
                'languages': language,
                'limit': min(limit, 100)  # Max limit is 100
            }
            
            # Add optional parameters
            if country:
                params['countries'] = country
            
            if keywords:
                params['keywords'] = keywords
            
            try:
                # Make request to Mediastack API
                print(f"[NEWS] GET {self.base_url} params={params}")
                response = requests.get(self.base_url, params=params, timeout=10)
                print(f"[NEWS] HTTP {response.status_code}")
            except Exception as net_exc:
                print(f"[NEWS] Network error querying MediaStack: {net_exc}")
                return {'success': False, 'error': f'Network error: {net_exc}', 'data': []}

            if response.status_code == 200:
                data = response.json()
                
                # Handle API errors
                if 'error' in data:
                    print(f"[NEWS] Mediastack error: {data['error']}")
                    return {
                        "success": False,
                        "error": data.get('error', {}).get('info', 'API error'),
                        "data": []
                    }
                result = {
                    "success": True,
                    "data": data.get('data', []),
                    "total": len(data.get('data', [])),
                    "timestamp": datetime.now().isoformat(),
                    "category": category
                }
                # Cache successful response
                self._set_cache(cache_key, result)
                return result
            elif response.status_code == 429:
                # Rate limit exceeded - return mock data
                print(f"[NEWS] Rate limit exceeded (HTTP 429). Using mock news.")
                return self._get_mock_news(category, keywords, limit)
            else:
                print(f"[NEWS] Non-200 HTTP: {response.status_code} body={response.text[:500]}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}",
                    "data": []
                }
                
        except requests.exceptions.RequestException as e:
            print(f"[NEWS] Network exception {e}")
            # Network error - return mock data
            return self._get_mock_news(category, keywords, limit)
        except Exception as e:
            print(f"[NEWS] Unexpected error: {e}")
            return {
                "success": False,
                "error": f"Server error: {str(e)}",
                "data": []
            }
    
    def _get_mock_news(self, category: str, keywords: Optional[str], limit: int) -> Dict:
        """Get mock legal news data when API is unavailable"""
        mock_news = [
            {
                "title": "Supreme Court Upholds Right to Privacy in Digital Age",
                "description": "The Supreme Court of India has issued a landmark judgment affirming the fundamental right to privacy in the digital era, setting new precedents for data protection laws.",
                "author": "Legal Correspondent",
                "source": "Supreme Court of India",
                "category": "constitutional_law",
                "country": "in",
                "published_at": "2024-10-28T10:00:00Z",
                "url": "https://main.sci.gov.in/supremecourt/2024/12345"
            },
            {
                "title": "New Companies Act Amendments Come into Effect",
                "description": "Recent amendments to the Companies Act 2013 focusing on corporate governance and compliance requirements have been implemented across India.",
                "author": "Corporate Law Reporter",
                "source": "Ministry of Corporate Affairs",
                "category": "corporate_law",
                "country": "in",
                "published_at": "2024-10-27T15:30:00Z",
                "url": "https://www.mca.gov.in"
            },
            {
                "title": "High Court Rules on Property Dispute Resolution",
                "description": "Delhi High Court delivers significant judgment on property dispute resolution mechanisms, clarifying procedures for civil litigation.",
                "author": "Property Law Expert",
                "source": "Delhi High Court",
                "category": "civil_law",
                "country": "in",
                "published_at": "2024-10-26T12:15:00Z",
                "url": "https://delhihighcourt.nic.in"
            },
            {
                "title": "Criminal Law Reforms: New Sentencing Guidelines",
                "description": "The Law Commission of India proposes comprehensive reforms to criminal sentencing guidelines, focusing on rehabilitation and restorative justice.",
                "author": "Criminal Law Analyst",
                "source": "Law Commission of India",
                "category": "criminal_law",
                "country": "in",
                "published_at": "2024-10-25T09:45:00Z",
                "url": "https://lawcommissionofindia.nic.in"
            },
            {
                "title": "Constitutional Amendment Bill Introduced in Parliament",
                "description": "A new constitutional amendment bill addressing fundamental rights and directive principles has been introduced in the Lok Sabha for consideration.",
                "author": "Constitutional Expert",
                "source": "Parliament of India",
                "category": "constitutional_law",
                "country": "in",
                "published_at": "2024-10-24T14:20:00Z",
                "url": "https://loksabha.nic.in"
            },
            {
                "title": "Legal Tech Innovation: AI in Court Proceedings",
                "description": "Indian courts are increasingly adopting artificial intelligence tools for case management and legal research, revolutionizing the judicial process.",
                "author": "Legal Tech Reporter",
                "source": "Indian Judiciary",
                "category": "legal_updates",
                "country": "in",
                "published_at": "2024-10-23T11:30:00Z",
                "url": "https://ecourts.gov.in"
            },
            {
                "title": "Consumer Protection Act: Enhanced Rights for Buyers",
                "description": "The Consumer Protection Act 2019 has been strengthened with new provisions protecting consumer rights in e-commerce and digital transactions.",
                "author": "Consumer Rights Advocate",
                "source": "Consumer Affairs Ministry",
                "category": "civil_law",
                "country": "in",
                "published_at": "2024-10-22T16:00:00Z",
                "url": "https://consumeraffairs.nic.in"
            },
            {
                "title": "Environmental Law: New Carbon Credit Regulations",
                "description": "The Ministry of Environment introduces new regulations for carbon credit trading, aligning with India's climate change commitments.",
                "author": "Environmental Law Expert",
                "source": "Ministry of Environment",
                "category": "legislation",
                "country": "in",
                "published_at": "2024-10-21T13:45:00Z",
                "url": "https://moef.gov.in"
            }
        ]
        
        # Filter by category if specified
        if category != 'general':
            filtered_news = [news for news in mock_news if news.get('category') == category]
        else:
            filtered_news = mock_news
        
        # Filter by keywords if specified
        if keywords:
            keywords_lower = keywords.lower()
            filtered_news = [news for news in filtered_news 
                           if keywords_lower in news['title'].lower() or 
                              keywords_lower in news['description'].lower()]
        
        # Limit results
        filtered_news = filtered_news[:limit]
        
        return {
            "success": True,
            "data": filtered_news,
            "total": len(filtered_news),
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "note": "Mock data - API rate limit exceeded"
        }

    def search_news(
        self,
        query: str,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: str = 'en',
        limit: int = 25
    ) -> Dict:
        """
        Search news by keywords with fallback to mock data
        
        Args:
            query: Search keywords
            category: Optional category filter
            country: Optional country filter
            language: Language code
            limit: Number of results
            
        Returns:
            Dict with success status and search results
        """
        try:
            return self.get_news(
                category=category or 'general',
                country=country,
                language=language,
                limit=limit,
                keywords=query
            )
        except Exception:
            # Fallback to mock data for search
            return self._get_mock_news(category or 'general', query, limit)
    
    def get_legal_categories(self) -> Dict:
        """
        Get available legal news categories
        
        Returns:
            Dict with legal categories
        """
        categories = [
            {
                "name": "legal_updates",
                "description": "Latest updates and developments in law and legal systems",
                "category": "general"
            },
            {
                "name": "court_judgments",
                "description": "Recent judgments and orders from Supreme Court, High Courts, and District Courts",
                "category": "general"
            },
            {
                "name": "legislation",
                "description": "New bills, amendments, acts, and statutory changes",
                "category": "general"
            },
            {
                "name": "criminal_law",
                "description": "News and cases related to criminal offenses, trials, and investigations",
                "category": "general"
            },
            {
                "name": "civil_law",
                "description": "Civil disputes, property law, contract law, and tort-related matters",
                "category": "general"
            },
            {
                "name": "corporate_law",
                "description": "Company law, mergers, compliance, and regulatory news",
                "category": "business"
            },
            {
                "name": "constitutional_law",
                "description": "Articles, fundamental rights issues, PILs, and constitutional cases",
                "category": "general"
            }
        ]
        
        return {
            "success": True,
            "categories": categories,
            "total": len(categories)
        }

"""
Internal helpers above
"""

# Create a singleton instance
news_service = NewsService()
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
