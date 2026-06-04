"""
CNR Service for LegalEase
Adapted from the original CNR automation for API integration
"""

import os
import time
import base64
from io import BytesIO
from typing import Dict, Optional
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.options import Options
from PIL import Image
from google import genai
from google.genai import types
import requests
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

class CNRService:
    def __init__(self):
        """Initialize the CNR service with Gemini API and Selenium"""
        self.api_key = os.getenv('GEMINI_API_KEY') or 'AIzaSyBL2hWedqA1keM2VK5TR94unIpm-nViYk0'
        
        # Initialize Gemini client
        os.environ['GOOGLE_API_KEY'] = self.api_key
        self.genai_client = genai.Client(api_key=self.api_key)
        
        # Setup Firefox driver
        self.driver = None
        
    def setup_driver(self):
        """Setup Firefox WebDriver with headless options for production"""
        try:
            firefox_options = Options()
            firefox_options.add_argument('--headless')  # Run headless for production
            firefox_options.add_argument('--no-sandbox')
            firefox_options.add_argument('--disable-dev-shm-usage')
            # Set preferences to avoid detection
            firefox_options.set_preference('dom.webdriver.enabled', False)
            firefox_options.set_preference('useAutomationExtension', False)
            
            # Try to find Firefox binary
            firefox_binary_paths = [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                "/usr/bin/firefox",
                "/usr/local/bin/firefox"
            ]
            
            firefox_binary = None
            for path in firefox_binary_paths:
                if os.path.exists(path):
                    firefox_binary = path
                    break
            
            if firefox_binary:
                firefox_options.binary_location = firefox_binary
            
            self.driver = webdriver.Firefox(
                service=Service(GeckoDriverManager().install()),
                options=firefox_options
            )
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            # Tighten timeouts to avoid long blocking requests
            try:
                self.driver.set_page_load_timeout(30)
                self.driver.set_script_timeout(30)
            except Exception:
                pass
            
        except Exception as e:
            raise Exception(f"Failed to setup Firefox driver: {str(e)}. Please ensure Firefox is installed and accessible.")
        
    def capture_captcha_image(self, element):
        """Capture CAPTCHA image from webpage"""
        try:
            # Take screenshot of the CAPTCHA element
            captcha_screenshot = element.screenshot_as_png
            return captcha_screenshot
        except Exception as e:
            print(f"Error capturing CAPTCHA: {e}")
            return None
    
    def solve_captcha_with_gemini(self, image_bytes):
        """Use Gemini Vision API to solve CAPTCHA"""
        try:
            # Create image part
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type='image/png'
            )
            
            # Prompt for CAPTCHA solving
            prompt = """You are a CAPTCHA solver. Analyze this CAPTCHA image carefully.
            
Instructions:
1. Look at the text/numbers in the CAPTCHA image
2. The CAPTCHA might contain letters, numbers, or both
3. Return ONLY the exact text you see, nothing else
4. Ignore any distortion, lines, or noise
5. Do not include any explanation, just the CAPTCHA text

CAPTCHA text:"""
            
            # Generate content with Gemini
            response = self.genai_client.models.generate_content(
                model='models/gemini-2.5-flash',
                contents=[prompt, image_part]
            )
            
            captcha_text = response.text.strip()
            return captcha_text
            
        except Exception as e:
            print(f"Error solving CAPTCHA with Gemini: {e}")
            return None
    
    def navigate_to_cnr_page(self):
        """Navigate to eCourts CNR Status page"""
        try:
            self.driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")
            time.sleep(3)
            
            # Click on CNR link
            wait = WebDriverWait(self.driver, 10)
            
            # Try multiple selectors for CNR link
            cnr_selectors = [
                "//a[contains(text(), 'CNR')]",
                "//a[contains(@href, 'cnr')]",
                "//a[contains(text(), 'Case Status')]"
            ]
            
            for selector in cnr_selectors:
                try:
                    cnr_link = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    cnr_link.click()
                    time.sleep(3)
                    break
                except:
                    continue
            
            return True
        except Exception as e:
            print(f"Error navigating: {e}")
            return False
    
    def fill_cnr_and_solve_captcha(self, cnr_number):
        """Fill CNR number and solve CAPTCHA"""
        try:
            wait = WebDriverWait(self.driver, 15)
            
            # Find CNR input field
            cnr_input = wait.until(EC.presence_of_element_located((
                By.XPATH, "//input[@id='cnr_number' or @name='cnr_number' or contains(@placeholder, 'CNR')]"
            )))
            cnr_input.clear()
            cnr_input.send_keys(cnr_number)
            
            # Locate CAPTCHA image
            captcha_img = wait.until(EC.presence_of_element_located((
                By.XPATH, "//img[contains(@id, 'captcha') or contains(@src, 'captcha')]"
            )))
            
            # Capture CAPTCHA
            captcha_bytes = self.capture_captcha_image(captcha_img)
            if not captcha_bytes:
                return False
            
            # Solve CAPTCHA with Gemini
            captcha_text = self.solve_captcha_with_gemini(captcha_bytes)
            if not captcha_text:
                return False
            
            # Enter CAPTCHA
            captcha_input = wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, "#fcaptcha_code"
            )))
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            
            # Click search button
            submit_btn = wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR, "#searchbtn"
            )))
            submit_btn.click()
            
            time.sleep(3)
            return True
            
        except Exception as e:
            print(f"Error filling form: {e}")
            return False
    
    def extract_cnr_status(self):
        """Extract CNR status information from the page"""
        try:
            wait = WebDriverWait(self.driver, 10)
            time.sleep(3)
            
            # Get page source
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')
            
            # Extract all visible text
            data = {}
            
            # Try to find tables with case information
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        key = cols[0].get_text(strip=True)
                        value = cols[1].get_text(strip=True)
                        if key and value:
                            data[key] = value
            
            # If no table found, extract divs with class patterns
            if not data:
                divs = soup.find_all(['div', 'span'], class_=lambda x: x and ('case' in x.lower() or 'status' in x.lower()))
                for div in divs:
                    text = div.get_text(strip=True)
                    if text:
                        data['info'] = data.get('info', '') + ' ' + text
            
            return data
            
        except Exception as e:
            print(f"Error extracting status: {e}")
            return {}
    
    def summarize_with_gemini(self, case_data):
        """Generate summary of case information using Gemini"""
        try:
            # Prepare case data as text
            case_text = "Case Status Information:\n\n"
            for key, value in case_data.items():
                case_text += f"{key}: {value}\n"
            
            prompt = f"""Analyze the following court case information and provide a clear, structured summary.

{case_text}

Please provide:
1. Case Summary - Brief overview of the case
2. Key Details - Important information like case number, parties involved, court name
3. Current Status - What is the current state of the case
4. Important Dates - Any dates mentioned
5. Petitioner and Respondent Names
6. Any other information that is relevant to the case
7. full information 
8. Always give clear answers in plain text only — avoid Markdown or special symbols like (* # -)

Format your response in a clear, easy-to-read manner."""
            
            response = self.genai_client.models.generate_content(
                model='models/gemini-2.5-flash',
                contents=prompt
            )
            
            summary = response.text
            return summary
            
        except Exception as e:
            print(f"Error generating summary: {e}")
            return "Could not generate summary"
    
    def lookup_cnr(self, cnr_number: str) -> Dict:
        """Main method to lookup CNR and return structured data"""
        try:
            # Setup driver
            self.setup_driver()
            
            # Navigate to CNR page
            if not self.navigate_to_cnr_page():
                return {
                    "success": False,
                    "error": "Failed to navigate to CNR page",
                    "data": {},
                    "summary": ""
                }
            
            # Fill form and solve CAPTCHA
            if not self.fill_cnr_and_solve_captcha(cnr_number):
                return {
                    "success": False,
                    "error": "Failed to submit form or solve CAPTCHA",
                    "data": {},
                    "summary": ""
                }
            
            # Extract status
            case_data = self.extract_cnr_status()
            if not case_data:
                case_data = {"error": "Could not extract case data automatically"}
            
            # Generate summary
            summary = self.summarize_with_gemini(case_data)
            
            return {
                "success": True,
                "error": None,
                "data": case_data,
                "summary": summary,
                "cnr_number": cnr_number,
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            error_msg = str(e)
            if "Firefox" in error_msg or "binary" in error_msg.lower():
                return {
                    "success": False,
                    "error": "Firefox browser not found. Please install Mozilla Firefox to use CNR lookup feature. Download from: https://www.mozilla.org/firefox/",
                    "data": {},
                    "summary": ""
                }
            return {
                "success": False,
                "error": f"Error in CNR lookup: {error_msg}",
                "data": {},
                "summary": ""
            }
        
        finally:
            # Clean up driver
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass

# Create a singleton instance
cnr_service = CNRService()
