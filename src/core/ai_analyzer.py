import json
from typing import Dict, Any, Optional, Tuple
import requests
from loguru import logger
from src.config.settings import settings


class AIAnalyzer:
    """AI analyzer using DeepSeek API"""

    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.api_base = settings.deepseek_api_base
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def analyze_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze email content using AI

        Returns:
            Dict with analysis results
        """
        try:
            # Prepare prompt for analysis
            prompt = self._create_analysis_prompt(email_data)

            # Call DeepSeek API
            response = self._call_deepseek_api(prompt)

            # Parse response
            analysis_result = self._parse_analysis_response(response, email_data)

            logger.info(f"AI analysis completed for email {email_data.get('id', 'unknown')}")
            return analysis_result

        except Exception as e:
            logger.error(f"Error analyzing email: {e}")
            return {
                "is_business": False,
                "category": "error",
                "urgency": "low",
                "summary": "",
                "suggested_action": "review_manually",
                "confidence": 0.0,
                "error": str(e)
            }

    def _create_analysis_prompt(self, email_data: Dict[str, Any]) -> str:
        """Create prompt for email analysis"""
        subject = email_data.get("subject", "")
        content = email_data.get("content", "")
        from_email = email_data.get("from_email", "")

        prompt = f"""Please analyze the following email content to determine if it is a business inquiry email, and provide detailed analysis:

Sender: {from_email}
Subject: {subject}
Content:
{content[:2000]}  # Limit content length

Please provide analysis results in the following format:
1. Whether it is a business inquiry email (Yes/No) and reasons
2. Email category (e.g., product inquiry, technical support, collaboration request, general inquiry, etc.)
3. Urgency level (high/medium/low)
4. Email content summary (50-100 words)
5. Suggested handling method (reply immediately, reply later, forward to others, no reply needed)
6. Analysis confidence (decimal between 0-1)

Please return the result in JSON format with the following fields:
- is_business: boolean
- category: string
- urgency: string (high/medium/low)
- summary: string
- suggested_action: string
- confidence: float
- reasoning: string (brief explanation of judgment reasons)"""

        return prompt

    def _call_deepseek_api(self, prompt: str) -> Dict[str, Any]:
        """Call DeepSeek API"""
        try:
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a professional email analysis assistant, skilled at judging email types and urgency levels."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000,
                "temperature": 0.3
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
            logger.debug(f"DeepSeek API usage: {usage}")

            return {"content": content, "usage": usage}

        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse DeepSeek API response: {e}")
            raise

    def _parse_analysis_response(self, response: Dict[str, Any], email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse AI response into structured format"""
        try:
            content = response.get("content", "")
            usage = response.get("usage", {})

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
                    analysis_data = json.loads(json_match)
                except json.JSONDecodeError:
                    # If JSON parsing fails, try to extract key information
                    analysis_data = self._extract_info_from_text(content)
            else:
                analysis_data = self._extract_info_from_text(content)

            # Ensure required fields exist
            result = {
                "is_business": analysis_data.get("is_business", False),
                "category": analysis_data.get("category", "unknown"),
                "urgency": analysis_data.get("urgency", "low"),
                "summary": analysis_data.get("summary", ""),
                "suggested_action": analysis_data.get("suggested_action", "review_manually"),
                "confidence": float(analysis_data.get("confidence", 0.5)),
                "reasoning": analysis_data.get("reasoning", ""),
                "token_usage": usage,
                "raw_response": content[:500]  # Store truncated raw response
            }

            # Validate and normalize values
            result["urgency"] = result["urgency"].lower()
            if result["urgency"] not in ["high", "medium", "low"]:
                result["urgency"] = "low"

            result["confidence"] = max(0.0, min(1.0, result["confidence"]))

            return result

        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return {
                "is_business": False,
                "category": "error",
                "urgency": "low",
                "summary": "",
                "suggested_action": "review_manually",
                "confidence": 0.0,
                "reasoning": f"Parse error: {str(e)}",
                "token_usage": {},
                "raw_response": content[:500] if 'content' in locals() else ""
            }

    def _extract_info_from_text(self, text: str) -> Dict[str, Any]:
        """Extract information from text response when JSON parsing fails"""
        result = {
            "is_business": False,
            "category": "unknown",
            "urgency": "low",
            "summary": "",
            "suggested_action": "review_manually",
            "confidence": 0.5,
            "reasoning": ""
        }

        text_lower = text.lower()

        # Extract business flag
        if "business inquiry" in text_lower or "is business email" in text_lower or "yes" in text_lower[:100]:
            result["is_business"] = True

        # Extract urgency
        if "high urgency" in text_lower or "urgent" in text_lower:
            result["urgency"] = "high"
        elif "medium urgency" in text_lower:
            result["urgency"] = "medium"

        # Extract category
        categories = ["product inquiry", "technical support", "collaboration request", "general inquiry", "sales inquiry", "customer service"]
        for category in categories:
            if category in text_lower:
                result["category"] = category
                break

        # Extract summary (first 100 characters after "summary")
        summary_match = re.search(r'summary[:：]\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()[:200]

        # Extract confidence if mentioned
        confidence_match = re.search(r'confidence[:：]\s*([0-9.]+)', text, re.IGNORECASE)
        if confidence_match:
            try:
                result["confidence"] = float(confidence_match.group(1))
            except ValueError:
                pass

        return result

    def estimate_token_usage(self, text: str) -> int:
        """Estimate token usage for a text (rough approximation)"""
        # Simple estimation: ~4 characters per token for Chinese/English mixed text
        return len(text) // 4

import re  # Add import at the top