import os
import base64
import email
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from loguru import logger
from src.config.settings import settings


class GmailClient:
    """Gmail API client for email operations"""

    def __init__(self):
        self.service = None
        self.credentials = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API"""
        try:
            creds = None

            # Parse scopes from string to list
            scopes_list = settings.gmail_scopes.split(",")

            # Check if token exists
            if os.path.exists(settings.gmail_token_path):
                creds = Credentials.from_authorized_user_file(
                    settings.gmail_token_path, scopes_list
                )

            # If there are no (valid) credentials available, let the user log in
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(settings.gmail_credentials_path):
                        raise FileNotFoundError(
                            f"Credentials file not found at {settings.gmail_credentials_path}. "
                            "Please download from Google Cloud Console."
                        )

                    flow = InstalledAppFlow.from_client_secrets_file(
                        settings.gmail_credentials_path, scopes_list
                    )
                    creds = flow.run_local_server(port=0)

                # Save the credentials for the next run
                with open(settings.gmail_token_path, "w") as token:
                    token.write(creds.to_json())

            self.credentials = creds
            self.service = build("gmail", "v1", credentials=creds)
            logger.info("Gmail authentication successful")

        except Exception as e:
            logger.error(f"Gmail authentication failed: {e}")
            raise

    def get_unread_emails(self, max_results: int = None) -> List[Dict[str, Any]]:
        """Get unread emails from inbox"""
        try:
            if max_results is None:
                max_results = settings.max_emails_per_check

            # Get unread messages
            results = self.service.users().messages().list(
                userId="me",
                labelIds=["INBOX", "UNREAD"],
                maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            emails = []

            for msg in messages:
                try:
                    email_data = self._get_email_details(msg["id"])
                    emails.append(email_data)
                except Exception as e:
                    logger.error(f"Error processing email {msg['id']}: {e}")
                    continue

            logger.info(f"Retrieved {len(emails)} unread emails")
            return emails

        except HttpError as error:
            logger.error(f"Error getting unread emails: {error}")
            return []

    def _get_email_details(self, msg_id: str) -> Dict[str, Any]:
        """Get detailed email information"""
        try:
            message = self.service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers = message["payload"]["headers"]
            subject = ""
            from_email = ""
            to_email = ""
            date_str = ""

            for header in headers:
                name = header["name"].lower()
                value = header["value"]

                if name == "subject":
                    subject = value
                elif name == "from":
                    from_email = value
                elif name == "to":
                    to_email = value
                elif name == "date":
                    date_str = value

            # Parse email body
            body = self._extract_email_body(message["payload"])

            # Parse date
            try:
                # Try to parse the date string
                received_at = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            except (ValueError, TypeError):
                received_at = datetime.utcnow()

            return {
                "id": msg_id,
                "thread_id": message.get("threadId", ""),
                "from_email": from_email,
                "to_email": to_email,
                "subject": subject,
                "content": body,
                "received_at": received_at,
                "snippet": message.get("snippet", ""),
                "labels": message.get("labelIds", [])
            }

        except Exception as e:
            logger.error(f"Error getting email details for {msg_id}: {e}")
            raise

    def _extract_email_body(self, payload: Dict) -> str:
        """Extract email body from payload"""
        body = ""

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if "data" in part["body"]:
                        body += base64.urlsafe_b64decode(
                            part["body"]["data"]
                        ).decode("utf-8", errors="ignore")
                elif part["mimeType"] == "text/html":
                    if "data" in part["body"]:
                        # For HTML emails, we'll extract text content
                        html_content = base64.urlsafe_b64decode(
                            part["body"]["data"]
                        ).decode("utf-8", errors="ignore")
                        # Simple HTML to text conversion
                        import re
                        text_content = re.sub(r'<[^>]+>', ' ', html_content)
                        text_content = re.sub(r'\s+', ' ', text_content).strip()
                        body += text_content
                elif "parts" in part:
                    # Recursively check nested parts
                    body += self._extract_email_body(part)

        elif "body" in payload and "data" in payload["body"]:
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="ignore")

        return body.strip()

    def mark_as_read(self, msg_id: str) -> bool:
        """Mark email as read"""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            logger.info(f"Marked email {msg_id} as read")
            return True
        except HttpError as error:
            logger.error(f"Error marking email as read: {error}")
            return False

    def create_draft(self, to_email: str, subject: str, content: str) -> Optional[str]:
        """Create a draft email"""
        try:
            message = MIMEText(content)
            message["to"] = to_email
            message["subject"] = subject

            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft = self.service.users().drafts().create(
                userId="me",
                body={"message": {"raw": encoded_message}}
            ).execute()

            draft_id = draft["id"]
            logger.info(f"Created draft {draft_id} for {to_email}")
            return draft_id

        except HttpError as error:
            logger.error(f"Error creating draft: {error}")
            return None

    def get_recent_emails(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get emails from the last N hours"""
        try:
            # Calculate timestamp for N hours ago
            after_time = datetime.utcnow() - timedelta(hours=hours)
            after_timestamp = int(after_time.timestamp())

            query = f"after:{after_timestamp}"

            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=settings.max_emails_per_check
            ).execute()

            messages = results.get("messages", [])
            emails = []

            for msg in messages:
                try:
                    email_data = self._get_email_details(msg["id"])
                    emails.append(email_data)
                except Exception as e:
                    logger.error(f"Error processing recent email {msg['id']}: {e}")
                    continue

            logger.info(f"Retrieved {len(emails)} emails from last {hours} hours")
            return emails

        except HttpError as error:
            logger.error(f"Error getting recent emails: {error}")
            return []