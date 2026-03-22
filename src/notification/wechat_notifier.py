import json
from typing import Dict, Any, Optional
import requests
from loguru import logger
from src.config.settings import settings


class WeChatNotifier:
    """WeChat notification sender"""

    def __init__(self):
        self.webhook_url = settings.wechat_webhook_url
        self.enabled = bool(self.webhook_url)

    def send_notification(self, email_data: Dict[str, Any], analysis_result: Dict[str, Any],
                         draft_created: bool = False, draft_id: Optional[str] = None) -> bool:
        """
        Send WeChat notification about processed email

        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            logger.warning("WeChat notification disabled - no webhook URL configured")
            return False

        try:
            message = self._create_notification_message(email_data, analysis_result, draft_created, draft_id)
            return self._send_webhook(message)

        except Exception as e:
            logger.error(f"Error sending WeChat notification: {e}")
            return False

    def _create_notification_message(self, email_data: Dict[str, Any], analysis_result: Dict[str, Any],
                                    draft_created: bool, draft_id: Optional[str]) -> Dict[str, Any]:
        """Create notification message for WeChat"""
        email_id = email_data.get("id", "unknown")
        subject = email_data.get("subject", "No Subject")
        from_email = email_data.get("from_email", "Unknown Sender")
        content_preview = email_data.get("content", "")[:100] + "..." if len(email_data.get("content", "")) > 100 else email_data.get("content", "")

        is_business = analysis_result.get("is_business", False)
        category = analysis_result.get("category", "Unknown Category")
        urgency = analysis_result.get("urgency", "Low")
        confidence = analysis_result.get("confidence", 0.0)

        # Determine notification type
        if not is_business:
            notification_type = "📧 Non-Business Email"
            color = "info"
        elif draft_created:
            notification_type = "📝 Draft Generated"
            color = "warning"
        else:
            notification_type = "🔍 Business Email Pending"
            color = "warning"

        # Create markdown message
        markdown_content = f"""### {notification_type}

**Email Information**
- **Sender**: {from_email}
- **Subject**: {subject}
- **Email ID**: {email_id}

**Analysis Results**
- **Category**: {category}
- **Urgency**: {urgency}
- **Confidence**: {confidence:.2f}
- **Is Business Email**: {"Yes" if is_business else "No"}

**Content Preview**
{content_preview}

**Processing Status**
- **Filter Status**: {"Filtered" if not is_business else "Passed"}
- **Draft Generated**: {"Yes" if draft_created else "No"}
- **Draft ID**: {draft_id if draft_id else "None"}

**Action Suggestions**
1. Log in to Gmail to view email details
2. Review AI-generated reply draft
3. Modify and send reply as needed"""

        # For WeChat webhook (assuming enterprise WeChat)
        message = {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_content
            }
        }

        # Add interactive buttons if draft was created
        if draft_created and draft_id:
            message["msgtype"] = "template_card"
            message["template_card"] = {
                "card_type": "button_interaction",
                "main_title": {
                    "title": notification_type,
                    "desc": f"From: {from_email}"
                },
                "sub_title_text": f"Subject: {subject}",
                "horizontal_content_list": [
                    {
                        "keyname": "Email Category",
                        "value": category
                    },
                    {
                        "keyname": "Urgency Level",
                        "value": urgency
                    },
                    {
                        "keyname": "Draft Status",
                        "value": "Generated"
                    }
                ],
                "card_action": {
                    "type": 1,
                    "url": f"https://mail.google.com/mail/u/0/#drafts?compose={draft_id}"
                },
                "button_list": [
                    {
                        "text": "View Draft",
                        "style": 1,
                        "key": "view_draft",
                        "url": f"https://mail.google.com/mail/u/0/#drafts?compose={draft_id}"
                    },
                    {
                        "text": "Mark as Processed",
                        "style": 2,
                        "key": "mark_processed"
                    }
                ]
            }

        return message

    def _send_webhook(self, message: Dict[str, Any]) -> bool:
        """Send message to WeChat webhook"""
        try:
            headers = {
                "Content-Type": "application/json"
            }

            response = requests.post(
                self.webhook_url,
                headers=headers,
                json=message,
                timeout=10
            )

            response.raise_for_status()
            result = response.json()

            if result.get("errcode") == 0:
                logger.info("WeChat notification sent successfully")
                return True
            else:
                logger.error(f"WeChat notification failed: {result.get('errmsg', 'Unknown error')}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"WeChat webhook request failed: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WeChat response: {e}")
            return False

    def send_simple_notification(self, title: str, content: str) -> bool:
        """Send a simple text notification"""
        if not self.enabled:
            return False

        try:
            message = {
                "msgtype": "text",
                "text": {
                    "content": f"{title}\n\n{content}"
                }
            }

            return self._send_webhook(message)

        except Exception as e:
            logger.error(f"Error sending simple notification: {e}")
            return False

    def send_batch_notification(self, notifications: list) -> bool:
        """Send batch notifications"""
        if not self.enabled:
            return False

        try:
            summary = f"📊 Email Processing Summary\n\nTotal processed {len(notifications)} emails:\n\n"

            business_count = 0
            draft_count = 0
            filtered_count = 0

            for i, notif in enumerate(notifications[:10], 1):  # Limit to 10 for readability
                email_data = notif.get("email_data", {})
                analysis_result = notif.get("analysis_result", {})

                subject = email_data.get("subject", "No Subject")[:30]
                from_email = email_data.get("from_email", "Unknown")
                is_business = analysis_result.get("is_business", False)
                draft_created = notif.get("draft_created", False)

                if not is_business:
                    filtered_count += 1
                    status = "Filtered"
                elif draft_created:
                    business_count += 1
                    draft_count += 1
                    status = "Draft Generated"
                else:
                    business_count += 1
                    status = "Pending"

                summary += f"{i}. {subject} - {from_email} ({status})\n"

            if len(notifications) > 10:
                summary += f"\n...and {len(notifications) - 10} more emails not shown"

            summary += f"\n\n📈 Statistics:\n"
            summary += f"- Business Emails: {business_count}\n"
            summary += f"- Drafts Generated: {draft_count}\n"
            summary += f"- Filtered Emails: {filtered_count}\n"
            summary += f"- Total: {len(notifications)}"

            message = {
                "msgtype": "markdown",
                "markdown": {
                    "content": summary
                }
            }

            return self._send_webhook(message)

        except Exception as e:
            logger.error(f"Error sending batch notification: {e}")
            return False