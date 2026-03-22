import json
from typing import Dict, Any, Optional, Tuple
import requests
from loguru import logger
from src.config.settings import settings


class DraftGenerator:
    """AI-powered email draft generator"""

    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.api_base = settings.deepseek_api_base
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def generate_draft(self, email_data: Dict[str, Any], analysis_result: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        Generate email draft response

        Returns:
            Tuple of (draft_subject, draft_content, metadata)
        """
        try:
            # Prepare prompt for draft generation
            prompt = self._create_draft_prompt(email_data, analysis_result)

            # Call DeepSeek API
            response = self._call_deepseek_api(prompt)

            # Parse response
            draft_subject, draft_content = self._parse_draft_response(response, email_data)

            if draft_subject and draft_content:
                metadata = {
                    "token_usage": response.get("usage", {}),
                    "model": "deepseek-chat",
                    "analysis_category": analysis_result.get("category", "unknown"),
                    "urgency": analysis_result.get("urgency", "low")
                }

                logger.info(f"Draft generated for email {email_data.get('id', 'unknown')}")
                return draft_subject, draft_content, metadata
            else:
                logger.warning(f"Failed to generate draft for email {email_data.get('id', 'unknown')}")
                return None, None, {}

        except Exception as e:
            logger.error(f"Error generating draft: {e}")
            return None, None, {"error": str(e)}

    def _create_draft_prompt(self, email_data: Dict[str, Any], analysis_result: Dict[str, Any]) -> str:
        """Create prompt for draft generation"""
        original_subject = email_data.get("subject", "")
        original_content = email_data.get("content", "")
        from_email = email_data.get("from_email", "")
        category = analysis_result.get("category", "unknown")
        urgency = analysis_result.get("urgency", "low")
        summary = analysis_result.get("summary", "")

        prompt = f"""Please draft a professional and personalized reply email based on the following email content and analysis results:

Original Email Information:
Sender: {from_email}
Subject: {original_subject}
Email Category: {category}
Urgency Level: {urgency}
Content Summary: {summary}

Original Email Content:
{original_content[:1500]}  # Limit content length

Please draft a reply email with the following requirements:
1. Subject: Add "Re: " before the original subject, keep it concise and clear
2. Salutation: Use appropriate salutation (such as Dear [Name], Hello, etc.)
3. Content Structure:
   - Thank the sender for their email
   - Respond to the email content
   - Provide necessary help or information
   - Express willingness for further communication
   - Polite closing remarks
4. Tone: Professional, friendly, and helpful
5. Length: 200-400 words

Please return the result in the following JSON format:
{{
    "subject": "Reply email subject",
    "content": "Complete email content",
    "notes": "Generation instructions or notes"
}}

Note: This email will be saved as a draft for manual review before sending."""

        return prompt

    def _call_deepseek_api(self, prompt: str) -> Dict[str, Any]:
        """Call DeepSeek API for draft generation"""
        try:
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a professional email writing assistant, skilled at drafting professional, polite, and effective business email replies."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1500,
                "temperature": 0.7,  # Slightly higher temperature for more creative responses
                "top_p": 0.9
            }

            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Log token usage for tracking
            usage = result.get("usage", {})
            logger.debug(f"Draft generation API usage: {usage}")

            return {"content": content, "usage": usage}

        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API request failed for draft generation: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse DeepSeek API response for draft: {e}")
            raise

    def _parse_draft_response(self, response: Dict[str, Any], email_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Parse draft response from AI"""
        try:
            content = response.get("content", "")
            original_subject = email_data.get("subject", "")

            # Try to extract JSON from response
            json_match = None
            json_patterns = [
                r'```json\s*(.*?)\s*```',
                r'```\s*(.*?)\s*```',
                r'\{.*\}'
            ]

            for pattern in json_patterns:
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    json_match = match.group(1) if pattern != r'\{.*\}' else match.group(0)
                    break

            if json_match:
                try:
                    draft_data = json.loads(json_match)
                    draft_subject = draft_data.get("subject", "")
                    draft_content = draft_data.get("content", "")

                    # Validate and clean up
                    if draft_subject and draft_content:
                        # Ensure subject has "Re: " prefix if not already
                        if not draft_subject.lower().startswith("re:"):
                            draft_subject = f"Re: {draft_subject}"

                        return draft_subject.strip(), draft_content.strip()
                except json.JSONDecodeError:
                    logger.warning("Failed to parse JSON from draft response, falling back to text extraction")

            # Fallback: extract subject and content from text
            return self._extract_draft_from_text(content, original_subject)

        except Exception as e:
            logger.error(f"Error parsing draft response: {e}")
            return None, None

    def _extract_draft_from_text(self, text: str, original_subject: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract draft from text response when JSON parsing fails"""
        try:
            lines = text.strip().split('\n')
            draft_content = ""
            draft_subject = f"Re: {original_subject}"

            # Look for subject line
            subject_patterns = [r'Subject[：:]?\s*(.*)', r'Title[：:]?\s*(.*)']
            for line in lines:
                for pattern in subject_patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        draft_subject = match.group(1).strip()
                        if not draft_subject.lower().startswith("re:"):
                            draft_subject = f"Re: {draft_subject}"
                        break

            # Extract content (skip subject lines and metadata)
            in_content = False
            for line in lines:
                line_lower = line.lower()

                # Skip metadata lines
                if any(keyword in line_lower for keyword in ['subject', 'title', '```', 'json', '{', '}']):
                    continue

                # Start capturing after empty line or specific markers
                if not in_content and (line.strip() == "" or 'content' in line_lower):
                    in_content = True
                    continue

                if in_content:
                    draft_content += line + '\n'

            # If no content extracted, use the whole text (excluding JSON markers)
            if not draft_content.strip():
                # Remove JSON markers and metadata
                clean_text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
                clean_text = re.sub(r'\{.*?\}', '', clean_text, flags=re.DOTALL)
                draft_content = clean_text.strip()

            # Ensure basic structure
            if draft_content:
                # Add greeting if missing
                if not any(greeting in draft_content[:100].lower() for greeting in ['dear', 'hello', 'hi', 'greetings']):
                    draft_content = f"Hello!\n\n{draft_content}"

                # Add closing if missing
                if not any(closing in draft_content[-100:].lower() for closing in ['best', 'regards', 'sincerely', 'thank you', 'thanks']):
                    draft_content = draft_content.rstrip() + "\n\nBest regards,\n\n[Your Name/Company Name]"

            return draft_subject.strip(), draft_content.strip()

        except Exception as e:
            logger.error(f"Error extracting draft from text: {e}")
            return None, None

    def generate_simple_acknowledgment(self, email_data: Dict[str, Any]) -> Tuple[str, str]:
        """Generate a simple acknowledgment draft for non-business emails"""
        from_email = email_data.get("from_email", "")
        original_subject = email_data.get("subject", "")

        # Extract name from email if possible
        name_match = re.search(r'([^<]+)<', from_email)
        if name_match:
            name = name_match.group(1).strip()
        else:
            name = from_email.split('@')[0] if '@' in from_email else ""

        subject = f"Re: {original_subject}"

        content = f"""Dear {name if name else "Customer"},

Hello!

Thank you for your email.

We have received your message and will process your request as soon as possible. If you have any questions, please feel free to contact us.

Best regards,

[Your Name/Company Name]
[Your Position]
[Company Name]
[Phone Number]
[Email Address]"""

        return subject, content

import re  # Add import at the top