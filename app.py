import os
import uuid
from flask import Flask, request, jsonify
from flask_restful import Resource, Api
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from db import qa_collection
from utils.pdf_parser import pdf_to_text
from utils.image_parser import image_to_text, check_tesseract_available
from adk_agent import agent
from cnr_service import cnr_service
from news_service import news_service
from career_service import career_service
from auth_service import auth_service
from LegalEase import ask_LegalEase
from cache_service import cache_service
from conversation_service import conversation_service

load_dotenv()
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend connection
api = Api(app)

# Limit upload size (e.g., 20 MB)
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH_MB', '20')) * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}

class Health(Resource):
    def get(self):
        return {"status": "ok"}

class LawGPT(Resource):
    def post(self):
        try:
            # Accept JSON or form-data with optional file upload
            content_type = request.content_type or ""
            data = {}
            if content_type.startswith("application/json"):
                data = request.get_json(force=True, silent=True) or {}
            else:
                # form-data
                data = request.form.to_dict()

            session_id = data.get("session_id") or str(uuid.uuid4())
            input_type = (data.get("type") or "text").lower()  # text, pdf, image
            text_content = None

            # Handle file upload if provided
            saved_path = None
            if "file" in request.files and request.files["file"]:
                file = request.files["file"]
                filename = secure_filename(file.filename or f"upload-{uuid.uuid4()}")
                saved_path = os.path.join(UPLOAD_DIR, filename)
                file.save(saved_path)
                try:
                    if input_type == "pdf":
                        if not filename.lower().endswith('.pdf'):
                            return {"error": "Please upload a valid PDF file"}, 400
                        text_content = pdf_to_text(saved_path)
                    elif input_type == "image":
                        _, ext = os.path.splitext(filename.lower())
                        if ext not in ALLOWED_IMAGE_EXTENSIONS:
                            return {"error": "Unsupported image format"}, 400
                        text_content = image_to_text(saved_path)
                    else:
                        # Treat as text file
                        try:
                            with open(saved_path, "r", encoding="utf-8", errors="ignore") as f:
                                text_content = f.read()
                        except Exception:
                            text_content = ""
                finally:
                    # Cleanup uploaded file
                    try:
                        if saved_path and os.path.exists(saved_path):
                            os.remove(saved_path)
                    except Exception:
                        pass
            else:
                # Fallback to content field (could be raw text or a file path)
                content = data.get("content", "")
                if input_type == "pdf" and content:
                    text_content = pdf_to_text(content)
                elif input_type == "image" and content:
                    text_content = image_to_text(content)
                else:
                    text_content = content

            if not text_content or not text_content.strip():
                return {"error": "No content provided or unable to extract text."}, 400

            # Check cache first for all types (text, pdf, image) - shared across all users
            cached_response = cache_service.get(input_type, text_content)
            if cached_response:
                print(f"[CACHE HIT] Returning cached response for {input_type} (global cache)")
                return cached_response, 200

            # Query the agent (which uses LegalEase under the hood and stores session memory)
            answer = agent.respond(text_content, session_id=session_id)

            # Persist Q&A (redundant to session memory but helpful for analytics)
            qa_collection.insert_one({
                "session_id": session_id,
                "question": text_content,
                "answer": answer,
            })

            response = {"session_id": session_id, "answer": answer}
            
            # Cache the response for all types (text, pdf, image) - shared across all users
            cache_service.set(input_type, text_content, response)

            return response, 200
        except Exception as e:
            # Always return JSON-serializable structure
            return {"error": str(e)}, 500

class CNRLookup(Resource):
    def post(self):
        try:
            data = request.get_json(force=True, silent=True) or {}
            cnr_number = data.get("cnr_number", "").strip()
            
            if not cnr_number:
                return {"error": "CNR number is required"}, 400
            
            # Validate CNR format (support common variants)
            # Accept either:
            # 1) 16-character alphanumeric (official CNR, e.g., DLSH010012342015, KABG020010432022)
            # 2) Hyphenated form (e.g., DLHC01-123456-2024)
            import re
            # Normalize: remove whitespace, uppercase, remove non-alphanumeric except hyphens
            normalized = re.sub(r'[^\w-]', '', cnr_number).upper()
            # Remove multiple consecutive hyphens and clean up
            normalized = re.sub(r'-+', '-', normalized).strip('-')
            
            cnr_16 = re.compile(r"^[A-Z0-9]{16}$")
            cnr_hyphen = re.compile(r"^[A-Z0-9]{2,10}-\d{1,7}-\d{4}$")
            
            if not (cnr_16.match(normalized) or cnr_hyphen.match(normalized)):
                return {"error": "Invalid CNR number format. Examples: DLSH010012342015 or DLHC01-123456-2024"}, 400
            
            # Use normalized value for lookup
            cnr_number = normalized
            
            # Check cache first
            cached_response = cache_service.get("cnr", cnr_number)
            if cached_response:
                return cached_response, 200
            
            # Call CNR service
            result = cnr_service.lookup_cnr(cnr_number)
            
            if result["success"]:
                response = {
                    "success": True,
                    "cnr_number": cnr_number,
                    "data": result["data"],
                    "summary": result["summary"],
                    "timestamp": result["timestamp"]
                }
                # Cache successful CNR lookups
                cache_service.set("cnr", cnr_number, response)
                return response, 200
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "cnr_number": cnr_number
                }, 400
                
        except Exception as e:
            return {"error": f"CNR lookup failed: {str(e)}"}, 500

class News(Resource):
    def get(self):
        try:
            # Get query parameters
            category = request.args.get('category', 'general')
            country = request.args.get('country', None)
            language = request.args.get('language', 'en')
            limit = int(request.args.get('limit', '25'))
            keywords = request.args.get('keywords', None)
            
            # Call news service
            result = news_service.get_news(
                category=category,
                country=country,
                language=language,
                limit=limit,
                keywords=keywords
            )
            
            return result, 200
            
        except Exception as e:
            return {"error": f"News fetch failed: {str(e)}"}, 500

class NewsSearch(Resource):
    def get(self):
        try:
            query = request.args.get('query')
            
            if not query:
                return {"error": "Query parameter is required"}, 400
            
            category = request.args.get('category', None)
            country = request.args.get('country', None)
            language = request.args.get('language', 'en')
            limit = int(request.args.get('limit', '25'))
            
            # Call news service search
            result = news_service.search_news(
                query=query,
                category=category,
                country=country,
                language=language,
                limit=limit
            )
            
            return result, 200
            
        except Exception as e:
            return {"error": f"News search failed: {str(e)}"}, 500

class NewsCategories(Resource):
    def get(self):
        try:
            result = news_service.get_legal_categories()
            return result, 200
        except Exception as e:
            return {"error": f"Failed to fetch categories: {str(e)}"}, 500

class Career(Resource):
    def get(self):
        try:
            # Get query parameters
            location = request.args.get('location', 'India')
            rows = int(request.args.get('rows', '25'))
            
            # Call career service
            result = career_service.search_lawyer_jobs(location=location, rows=rows)
            
            return result, 200
            
        except Exception as e:
            return {"error": f"Career search failed: {str(e)}"}, 500

class CareerSearch(Resource):
    def post(self):
        try:
            data = request.get_json(force=True, silent=True) or {}
            
            location = data.get('location', 'India')
            keywords = data.get('keywords', '')
            rows = int(data.get('rows', '25'))
            
            # Call career service with keywords
            result = career_service.search_jobs_with_keywords(
                location=location,
                keywords=keywords,
                rows=rows
            )
            
            return result, 200
            
        except Exception as e:
            return {"error": f"Career search failed: {str(e)}"}, 500

class Signup(Resource):
    def post(self):
        try:
            data = request.get_json(force=True, silent=True) or {}
            email = data.get('email', '').strip()
            name = data.get('name', '').strip()
            password = data.get('password', '').strip()
            
            result = auth_service.signup(email, name, password)
            
            if result['success']:
                return result, 201
            else:
                return result, 400
                
        except Exception as e:
            return {"success": False, "error": f"Signup failed: {str(e)}"}, 500
    
    def options(self):
        # Handle CORS preflight
        return {}, 200

class Login(Resource):
    def post(self):
        try:
            data = request.get_json(force=True, silent=True) or {}
            email = data.get('email', '').strip()
            password = data.get('password', '').strip()
            
            result = auth_service.login(email, password)
            
            if result['success']:
                return result, 200
            else:
                return result, 401
                
        except Exception as e:
            return {"success": False, "error": f"Login failed: {str(e)}"}, 500
    
    def options(self):
        # Handle CORS preflight
        return {}, 200

class GetUser(Resource):
    def get(self):
        try:
            # Get token from Authorization header
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return {"success": False, "error": "No token provided"}, 401
            
            token = auth_header.split(' ')[1]
            user = auth_service.get_user_from_token(token)
            
            if user:
                return {"success": True, "user": user}, 200
            else:
                return {"success": False, "error": "Invalid token"}, 401
                
        except Exception as e:
            return {"success": False, "error": f"Failed to get user: {str(e)}"}, 500
    
    def options(self):
        # Handle CORS preflight
        return {}, 200

class ForgotPassword(Resource):
    def post(self):
        try:
            data = request.get_json(force=True, silent=True) or {}
            email = data.get('email', '').strip()
            
            result = auth_service.forgot_password(email)
            return result, 200
                
        except Exception as e:
            return {"success": False, "error": f"Password reset failed: {str(e)}"}, 500
    
    def options(self):
        # Handle CORS preflight
        return {}, 200

class Logout(Resource):
    def post(self):
        # For JWT, logout is handled client-side by removing the token
        return {"success": True, "message": "Logged out successfully"}, 200
    
    def options(self):
        # Handle CORS preflight
        return {}, 200

class ImageSummary(Resource):
    def post(self):
        try:
            # Accept multipart/form-data with field name 'image'
            if "image" not in request.files or not request.files["image"]:
                return {"error": "No image uploaded"}, 400

            img_file = request.files["image"]
            filename = secure_filename(img_file.filename or f"image-{uuid.uuid4()}.png")
            _, ext = os.path.splitext(filename.lower())
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                return {"error": "Unsupported image format"}, 400
            saved_path = os.path.join(UPLOAD_DIR, filename)
            img_file.save(saved_path)

            # Check Tesseract availability first
            is_available, tesseract_error = check_tesseract_available()
            if not is_available:
                try:
                    if saved_path and os.path.exists(saved_path):
                        os.remove(saved_path)
                except Exception:
                    pass
                return {"error": tesseract_error}, 422
            
            # OCR
            try:
                ocr_text = image_to_text(saved_path)
            finally:
                try:
                    if saved_path and os.path.exists(saved_path):
                        os.remove(saved_path)
                except Exception:
                    pass
            if not ocr_text or not ocr_text.strip():
                return {
                    "error": (
                        "OCR returned no text. The image may be empty, corrupted, or contain no readable text. "
                        "Please ensure the image is clear and contains text."
                    )
                }, 422

            # Check cache first
            cached_response = cache_service.get("image", ocr_text)
            if cached_response:
                print(f"[CACHE HIT] Returning cached image summary")
                return cached_response, 200

            # Summarization prompt for Ollama model (uses MODEL env via ask_LegalEase)
            prompt = (
                "You are a legal document summarizer. Summarize the following OCR text into a concise summary.\n\n"
                "IMPORTANT: Do NOT include sections like 'Legal Basis' or 'Next Hearing'. Just provide a clear, concise summary of the content.\n\n"
                f"OCR TEXT:\n{ocr_text}"
            )

            summary = ask_LegalEase(prompt, system_prompt=None)
            
            response = {"summary": summary}
            
            # Cache the response
            cache_service.set("image", ocr_text, response)

            return response, 200
        except Exception as e:
            return {"error": f"Image summary failed: {str(e)}"}, 500

    def options(self):
        # Handle CORS preflight
        return {}, 200

class PDFAnalysis(Resource):
    def post(self):
        try:
            # Accept multipart/form-data with field name 'file'
            if "file" not in request.files or not request.files["file"]:
                return {"error": "No PDF uploaded"}, 400

            pdf_file = request.files["file"]
            if not pdf_file.filename.lower().endswith('.pdf'):
                return {"error": "Please upload a valid PDF file"}, 400

            filename = secure_filename(pdf_file.filename or f"document-{uuid.uuid4()}.pdf")
            saved_path = os.path.join(UPLOAD_DIR, filename)
            pdf_file.save(saved_path)

            # Extract text using pdfplumber
            try:
                pdf_text = pdf_to_text(saved_path)
            finally:
                try:
                    if saved_path and os.path.exists(saved_path):
                        os.remove(saved_path)
                except Exception:
                    pass
            if not pdf_text.strip():
                return {"error": "PDF text extraction failed or no text detected"}, 400

            # Check cache first
            cached_response = cache_service.get("pdf", pdf_text)
            if cached_response:
                print(f"[CACHE HIT] Returning cached PDF analysis")
                return cached_response, 200

            # Analysis prompt for Ollama model (uses MODEL env via ask_LegalEase)
            prompt = (
                "You are a legal document analyzer. Analyze the following PDF document text and "
                "provide a comprehensive summary. Focus on:\n\n"
                "- Document type and purpose\n"
                "- Key legal points and clauses\n"
                "- Important dates, parties, and terms\n"
                "- Legal implications and recommendations\n\n"
                "IMPORTANT: Do NOT include sections like 'Legal Basis' or 'Next Hearing'. Just provide a clear, comprehensive analysis.\n\n"
                f"PDF TEXT:\n{pdf_text}"
            )

            analysis = ask_LegalEase(prompt, system_prompt=None)
            
            response = {"analysis": analysis}
            
            # Cache the response
            cache_service.set("pdf", pdf_text, response)

            return response, 200
        except Exception as e:
            return {"error": f"PDF analysis failed: {str(e)}"}, 500

    def options(self):
        # Handle CORS preflight
        return {}, 200

class CacheStats(Resource):
    """Get cache statistics"""
    def get(self):
        try:
            stats = cache_service.get_stats()
            return stats, 200
        except Exception as e:
            return {"error": str(e)}, 500

class CacheClear(Resource):
    """Clear cache by type or all"""
    def delete(self):
        try:
            data = request.get_json(silent=True) or {}
            cache_type = data.get("type")  # text, cnr, news, career, or None for all
            
            if cache_type:
                count = cache_service.clear_by_type(cache_type)
                return {"success": True, "message": f"Cleared {count} cache entries for type: {cache_type}", "count": count}, 200
            else:
                count = cache_service.clear_all()
                return {"success": True, "message": f"Cleared entire cache: {count} entries", "count": count}, 200
        except Exception as e:
            return {"error": str(e)}, 500

class ConversationList(Resource):
    """Get all conversations for a user"""
    def get(self):
        try:
            # Get user email from query params or auth header
            user_email = request.args.get('user_email')
            if not user_email:
                return {"error": "user_email is required"}, 400
            
            conversations = conversation_service.get_user_conversations(user_email)
            return {
                "success": True,
                "conversations": conversations,
                "total": len(conversations)
            }, 200
        except Exception as e:
            return {"error": str(e)}, 500
    
    def post(self):
        """Create a new conversation"""
        try:
            data = request.get_json(force=True, silent=True) or {}
            user_email = data.get("user_email")
            title = data.get("title", "New Conversation")
            
            if not user_email:
                return {"error": "user_email is required"}, 400
            
            conversation = conversation_service.create_conversation(user_email, title)
            return {
                "success": True,
                "conversation": conversation
            }, 201
        except Exception as e:
            return {"error": str(e)}, 500

class ConversationDetail(Resource):
    """Get, update, or delete a specific conversation"""
    def get(self, conversation_id):
        try:
            user_email = request.args.get('user_email')
            if not user_email:
                return {"error": "user_email is required"}, 400
            
            conversation = conversation_service.get_conversation(conversation_id, user_email)
            if not conversation:
                return {"error": "Conversation not found"}, 404
            
            return {
                "success": True,
                "conversation": conversation
            }, 200
        except Exception as e:
            return {"error": str(e)}, 500
    
    def patch(self, conversation_id):
        """Update conversation title"""
        try:
            data = request.get_json(force=True, silent=True) or {}
            user_email = data.get("user_email")
            title = data.get("title")
            
            if not user_email:
                return {"error": "user_email is required"}, 400
            if not title:
                return {"error": "title is required"}, 400
            
            success = conversation_service.update_conversation_title(conversation_id, user_email, title)
            if success:
                return {"success": True, "message": "Title updated"}, 200
            return {"error": "Failed to update title"}, 400
        except Exception as e:
            return {"error": str(e)}, 500
    
    def delete(self, conversation_id):
        """Delete a conversation"""
        try:
            user_email = request.args.get('user_email')
            if not user_email:
                return {"error": "user_email is required"}, 400
            
            success = conversation_service.delete_conversation(conversation_id, user_email)
            if success:
                return {"success": True, "message": "Conversation deleted"}, 200
            return {"error": "Failed to delete conversation"}, 400
        except Exception as e:
            return {"error": str(e)}, 500

class ConversationMessages(Resource):
    """Add messages to a conversation"""
    def post(self, conversation_id):
        try:
            data = request.get_json(force=True, silent=True) or {}
            user_email = data.get("user_email")
            role = data.get("role")  # user or assistant
            content = data.get("content")
            
            if not user_email or not role or not content:
                return {"error": "user_email, role, and content are required"}, 400
            
            success = conversation_service.add_message(conversation_id, user_email, role, content)
            if success:
                return {"success": True, "message": "Message added"}, 200
            return {"error": "Failed to add message"}, 400
        except Exception as e:
            return {"error": str(e)}, 500

api.add_resource(Health, "/health")
api.add_resource(LawGPT, "/ask")
api.add_resource(CNRLookup, "/cnr")
api.add_resource(News, "/news")
api.add_resource(NewsSearch, "/news/search")
api.add_resource(NewsCategories, "/news/categories")
api.add_resource(Career, "/career")
api.add_resource(CareerSearch, "/career/search")
# Authentication endpoints
api.add_resource(Signup, "/auth/signup")
api.add_resource(Login, "/auth/login")
api.add_resource(GetUser, "/auth/user")
api.add_resource(ForgotPassword, "/auth/forgot-password")
api.add_resource(Logout, "/auth/logout")
api.add_resource(ImageSummary, "/image/summary")
api.add_resource(PDFAnalysis, "/pdf/analysis")
# Cache management endpoints
api.add_resource(CacheStats, "/cache/stats")
api.add_resource(CacheClear, "/cache/clear")
# Conversation management endpoints
api.add_resource(ConversationList, "/conversations")
api.add_resource(ConversationDetail, "/conversations/<string:conversation_id>")
api.add_resource(ConversationMessages, "/conversations/<string:conversation_id>/messages")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))
