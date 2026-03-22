import re
from typing import Dict, Any, Tuple, Optional
from loguru import logger
from src.config.settings import settings


class MailFilter:
    """Email filtering logic"""

    def __init__(self):
        self.blacklisted_domains = settings.blacklisted_domains.split(",")
        self.blacklisted_subjects = settings.blacklisted_subjects.split(",")
        self.min_content_length = settings.min_content_length

    def filter_email(self, email_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Filter email based on various criteria

        Returns:
            Tuple[bool, Optional[str]]: (should_filter, reason)
        """
        try:
            # Check 1: Content length
            if len(email_data.get("content", "")) < self.min_content_length:
                return True, "Content too short"

            # Check 2: From email domain
            from_email = email_data.get("from_email", "").lower()
            if self._is_blacklisted_domain(from_email):
                return True, "Blacklisted domain"

            # Check 3: Subject keywords
            subject = email_data.get("subject", "").lower()
            if self._contains_blacklisted_keywords(subject):
                return True, "Blacklisted subject"

            # Check 4: No-reply addresses
            if self._is_no_reply_email(from_email):
                return True, "No-reply email"

            # Check 5: Newsletter patterns
            if self._is_newsletter(email_data):
                return True, "Newsletter pattern"

            # Check 6: Spam-like patterns
            if self._is_spam_like(email_data):
                return True, "Spam-like pattern"

            # Email passed all filters
            return False, None

        except Exception as e:
            logger.error(f"Error filtering email: {e}")
            return True, f"Filter error: {str(e)}"

    def _is_blacklisted_domain(self, email_address: str) -> bool:
        """Check if email domain is blacklisted"""
        # Extract domain from email
        domain_match = re.search(r'@([a-zA-Z0-9.-]+)', email_address)
        if not domain_match:
            return False

        domain = domain_match.group(1).lower()

        # Check against blacklisted domains
        for blacklisted in self.blacklisted_domains:
            if blacklisted.lower() in domain:
                return True

        return False

    def _contains_blacklisted_keywords(self, text: str) -> bool:
        """Check if text contains blacklisted keywords"""
        text_lower = text.lower()

        for keyword in self.blacklisted_subjects:
            if keyword.lower() in text_lower:
                return True

        # Additional common spam keywords
        spam_keywords = [
            "win", "free", "prize", "lottery", "urgent", "important",
            "act now", "limited time", "click here", "buy now",
            "discount", "offer", "sale", "deal"
        ]

        for keyword in spam_keywords:
            if keyword in text_lower:
                return True

        return False

    def _is_no_reply_email(self, email_address: str) -> bool:
        """Check if email is from a no-reply address"""
        email_lower = email_address.lower()

        no_reply_patterns = [
            "no-reply",
            "noreply",
            "donotreply",
            "do-not-reply",
            "no_reply",
            "noreply@",
            "no.reply"
        ]

        for pattern in no_reply_patterns:
            if pattern in email_lower:
                return True

        return False

    def _is_newsletter(self, email_data: Dict[str, Any]) -> bool:
        """Check if email is a newsletter"""
        subject = email_data.get("subject", "").lower()
        content = email_data.get("content", "").lower()

        newsletter_indicators = [
            "newsletter",
            "news letter",
            "weekly update",
            "monthly digest",
            "digest",
            "roundup",
            "round-up"
        ]

        # Check subject
        for indicator in newsletter_indicators:
            if indicator in subject:
                return True

        # Check content for unsubscribe links (common in newsletters)
        unsubscribe_patterns = [
            "unsubscribe",
            "opt-out",
            "opt out",
            "manage preferences",
            "email preferences"
        ]

        for pattern in unsubscribe_patterns:
            if pattern in content:
                return True

        return False

    def _is_spam_like(self, email_data: Dict[str, Any]) -> bool:
        """Check for spam-like patterns"""
        subject = email_data.get("subject", "").lower()
        content = email_data.get("content", "").lower()

        # Check for excessive punctuation
        if re.search(r'!!!+', subject) or re.search(r'\?\?\?+', subject):
            return True

        # Check for all caps in subject
        if len(subject) > 10 and subject.upper() == subject:
            return True

        # Check for suspicious URLs
        suspicious_domains = [
            ".xyz", ".top", ".club", ".win", ".bid", ".download",
            ".stream", ".online", ".site", ".website"
        ]

        for domain in suspicious_domains:
            if domain in content:
                return True

        # Check for excessive special characters
        special_char_ratio = len(re.findall(r'[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>/?]', subject)) / max(len(subject), 1)
        if special_char_ratio > 0.3:  # More than 30% special characters
            return True

        return False

    def is_potential_business_email(self, email_data: Dict[str, Any]) -> bool:
        """Check if email is potentially a business inquiry"""
        try:
            subject = email_data.get("subject", "").lower()
            content = email_data.get("content", "").lower()

            # Business-related keywords (English only for internationalization)
            business_keywords = [
                "inquiry", "enquiry", "question", "request",
                "proposal", "quote", "quotation", "estimate",
                "meeting", "appointment", "consultation",
                "project", "collaboration", "partnership",
                "service", "product", "solution",
                "help", "support", "assistance",
                "hello", "hi", "dear", "good morning", "good afternoon"
            ]

            # Check for business keywords
            for keyword in business_keywords:
                if keyword in subject or keyword in content:
                    return True

            # Check for question marks (indicating inquiry)
            if "?" in content:
                return True

            # Check for formal greeting patterns
            greeting_patterns = [
                r"dear\s+\w+",
                r"hello\s+\w+",
                r"hi\s+\w+",
                r"good\s+(morning|afternoon|evening)\s+\w+"
            ]

            for pattern in greeting_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking business email: {e}")
            return False