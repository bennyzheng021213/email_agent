#!/usr/bin/env python3
"""
Email Agent Main Program

This is the main entry point for the Email Management Agent.
It integrates all modules to provide automated email processing.
"""

import time
import schedule
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger

from src.core.gmail_client import GmailClient
from src.core.mail_filter import MailFilter
from src.core.ai_analyzer import AIAnalyzer
from src.core.draft_generator import DraftGenerator
from src.notification.wechat_notifier import WeChatNotifier
from src.database.models import SessionLocal, Email, Draft, ProcessingLog, create_tables
from src.config.settings import settings


class EmailAgent:
    """Main email agent class that orchestrates all components"""

    def __init__(self):
        logger.info("Initializing Email Agent...")

        # Initialize components
        self.gmail_client = GmailClient()
        self.mail_filter = MailFilter()
        self.ai_analyzer = AIAnalyzer()
        self.draft_generator = DraftGenerator()
        self.wechat_notifier = WeChatNotifier()

        # Initialize database
        create_tables()
        logger.info("Database initialized")

        # Statistics
        self.stats = {
            "total_processed": 0,
            "business_emails": 0,
            "drafts_created": 0,
            "filtered_emails": 0,
            "errors": 0
        }

        logger.info("Email Agent initialized successfully")

    def process_single_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single email through the pipeline"""
        result = {
            "email_id": email_data.get("id"),
            "processed": False,
            "is_business": False,
            "filtered": False,
            "draft_created": False,
            "error": None
        }

        try:
            email_id = email_data.get("id")
            logger.info(f"Processing email: {email_id}")

            # Check if already processed
            if self._is_email_processed(email_id):
                logger.info(f"Email {email_id} already processed, skipping")
                result["processed"] = True
                return result

            # Step 1: Filter email
            should_filter, filter_reason = self.mail_filter.filter_email(email_data)

            if should_filter:
                logger.info(f"Email {email_id} filtered: {filter_reason}")
                self._save_email_to_db(email_data, is_filtered=True, filter_reason=filter_reason)
                result["filtered"] = True
                result["processed"] = True
                return result

            # Step 2: AI Analysis
            analysis_result = self.ai_analyzer.analyze_email(email_data)
            is_business = analysis_result.get("is_business", False)

            # Save email with analysis results
            self._save_email_to_db(
                email_data,
                is_business=is_business,
                analysis_result=analysis_result
            )

            result["is_business"] = is_business
            result["analysis_result"] = analysis_result

            if not is_business:
                logger.info(f"Email {email_id} is not a business email")
                result["processed"] = True
                return result

            # Step 3: Generate draft for business emails
            draft_subject, draft_content, draft_metadata = self.draft_generator.generate_draft(
                email_data, analysis_result
            )

            if draft_subject and draft_content:
                # Step 4: Create draft in Gmail
                draft_id = self.gmail_client.create_draft(
                    to_email=email_data.get("from_email"),
                    subject=draft_subject,
                    content=draft_content
                )

                if draft_id:
                    # Save draft to database
                    self._save_draft_to_db(
                        email_id=email_id,
                        draft_content=draft_content,
                        draft_subject=draft_subject,
                        draft_metadata=draft_metadata
                    )

                    # Update email record
                    self._update_email_draft_info(email_id, draft_id)

                    # Step 5: Send WeChat notification
                    if self.wechat_notifier.enabled:
                        self.wechat_notifier.send_notification(
                            email_data=email_data,
                            analysis_result=analysis_result,
                            draft_created=True,
                            draft_id=draft_id
                        )

                    result["draft_created"] = True
                    result["draft_id"] = draft_id
                    self.stats["drafts_created"] += 1

                else:
                    logger.error(f"Failed to create draft for email {email_id}")
                    result["error"] = "Draft creation failed"

            else:
                logger.warning(f"Failed to generate draft content for email {email_id}")
                # Send notification even if draft generation failed
                if self.wechat_notifier.enabled:
                    self.wechat_notifier.send_notification(
                        email_data=email_data,
                        analysis_result=analysis_result,
                        draft_created=False
                    )

            # Mark email as read
            self.gmail_client.mark_as_read(email_id)

            result["processed"] = True
            self.stats["business_emails"] += 1

            logger.info(f"Successfully processed email {email_id}")

        except Exception as e:
            logger.error(f"Error processing email {email_data.get('id')}: {e}")
            result["error"] = str(e)
            self.stats["errors"] += 1

            # Log error to database
            self._log_processing_error(email_data.get("id"), str(e))

        return result

    def process_new_emails(self) -> List[Dict[str, Any]]:
        """Process all new unread emails"""
        logger.info("Checking for new emails...")

        try:
            # Get unread emails
            emails = self.gmail_client.get_unread_emails()

            if not emails:
                logger.info("No new emails found")
                return []

            results = []
            batch_notifications = []

            for email_data in emails:
                result = self.process_single_email(email_data)
                results.append(result)

                # Collect notifications for batch sending
                if result.get("is_business") and not result.get("error"):
                    batch_notifications.append({
                        "email_data": email_data,
                        "analysis_result": result.get("analysis_result", {}),
                        "draft_created": result.get("draft_created", False)
                    })

                # Update statistics
                self.stats["total_processed"] += 1
                if result.get("filtered"):
                    self.stats["filtered_emails"] += 1

            # Send batch notification if enabled
            if batch_notifications and self.wechat_notifier.enabled:
                self.wechat_notifier.send_batch_notification(batch_notifications)

            # Log statistics
            self._log_statistics(len(emails), results)

            return results

        except Exception as e:
            logger.error(f"Error processing new emails: {e}")
            self.stats["errors"] += 1
            return []

    def _is_email_processed(self, email_id: str) -> bool:
        """Check if email has already been processed"""
        db = SessionLocal()
        try:
            email = db.query(Email).filter(Email.id == email_id).first()
            return email is not None and email.is_processed
        finally:
            db.close()

    def _save_email_to_db(self, email_data: Dict[str, Any], **kwargs):
        """Save email to database"""
        db = SessionLocal()
        try:
            email = Email(
                id=email_data.get("id"),
                thread_id=email_data.get("thread_id"),
                from_email=email_data.get("from_email"),
                to_email=email_data.get("to_email"),
                subject=email_data.get("subject"),
                content=email_data.get("content", "")[:5000],  # Limit content length
                received_at=email_data.get("received_at"),
                is_processed=True,
                is_business=kwargs.get("is_business", False),
                is_filtered=kwargs.get("is_filtered", False),
                filter_reason=kwargs.get("filter_reason"),
                draft_created=False,
                wechat_notified=False
            )

            db.add(email)
            db.commit()

            # Log processing action
            action = "filtered" if kwargs.get("is_filtered") else "analyzed"
            details = f"Filter reason: {kwargs.get('filter_reason')}" if kwargs.get("is_filtered") else "AI analysis completed"

            log = ProcessingLog(
                email_id=email_data.get("id"),
                action=action,
                details=details
            )
            db.add(log)
            db.commit()

        except Exception as e:
            db.rollback()
            logger.error(f"Error saving email to database: {e}")
        finally:
            db.close()

    def _save_draft_to_db(self, email_id: str, draft_content: str, draft_subject: str, draft_metadata: Dict[str, Any]):
        """Save draft to database"""
        db = SessionLocal()
        try:
            draft = Draft(
                email_id=email_id,
                draft_content=draft_content,
                draft_subject=draft_subject,
                ai_model=draft_metadata.get("model", "deepseek-chat"),
                token_usage=draft_metadata.get("token_usage", {}).get("total_tokens", 0)
            )

            db.add(draft)
            db.commit()

            # Log draft creation
            log = ProcessingLog(
                email_id=email_id,
                action="draft_created",
                details=f"Draft generated with {draft_metadata.get('model')}"
            )
            db.add(log)
            db.commit()

        except Exception as e:
            db.rollback()
            logger.error(f"Error saving draft to database: {e}")
        finally:
            db.close()

    def _update_email_draft_info(self, email_id: str, draft_id: str):
        """Update email record with draft information"""
        db = SessionLocal()
        try:
            email = db.query(Email).filter(Email.id == email_id).first()
            if email:
                email.draft_created = True
                email.draft_id = draft_id
                email.wechat_notified = True
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating email draft info: {e}")
        finally:
            db.close()

    def _log_processing_error(self, email_id: str, error_msg: str):
        """Log processing error to database"""
        db = SessionLocal()
        try:
            log = ProcessingLog(
                email_id=email_id,
                action="error",
                details=f"Processing error: {error_msg}"
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.error(f"Error logging processing error: {e}")
        finally:
            db.close()

    def _log_statistics(self, total_emails: int, results: List[Dict[str, Any]]):
        """Log processing statistics"""
        business_count = sum(1 for r in results if r.get("is_business"))
        draft_count = sum(1 for r in results if r.get("draft_created"))
        filtered_count = sum(1 for r in results if r.get("filtered"))
        error_count = sum(1 for r in results if r.get("error"))

        logger.info(f"""
        Processing Statistics:
        ---------------------
        Total emails: {total_emails}
        Business emails: {business_count}
        Drafts created: {draft_count}
        Filtered emails: {filtered_count}
        Errors: {error_count}
        ---------------------
        """)

    def run_once(self):
        """Run email processing once"""
        logger.info("Starting single email processing run...")
        self.process_new_emails()
        logger.info("Single run completed")

    def run_continuously(self):
        """Run email processing continuously on schedule"""
        logger.info(f"Starting continuous email processing (interval: {settings.check_interval_seconds}s)")

        # Schedule the job
        schedule.every(settings.check_interval_seconds).seconds.do(
            lambda: self.process_new_emails()
        )

        # Initial run
        self.process_new_emails()

        # Keep running
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Email Agent stopped by user")
        except Exception as e:
            logger.error(f"Error in continuous run: {e}")

    def print_stats(self):
        """Print current statistics"""
        print(f"""
        Email Agent Statistics:
        ======================
        Total processed: {self.stats['total_processed']}
        Business emails: {self.stats['business_emails']}
        Drafts created: {self.stats['drafts_created']}
        Filtered emails: {self.stats['filtered_emails']}
        Errors: {self.stats['errors']}
        ======================
        """)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Email Management Agent")
    parser.add_argument("--mode", choices=["once", "continuous"], default="once",
                       help="Run mode: once (single run) or continuous (scheduled)")
    parser.add_argument("--interval", type=int, default=None,
                       help="Check interval in seconds (for continuous mode)")
    parser.add_argument("--test", action="store_true",
                       help="Test mode - don't actually send notifications or create drafts")

    args = parser.parse_args()

    # Configure logger
    logger.remove()  # Remove default handler
    logger.add(
        "email_agent.log",
        rotation="10 MB",
        retention="7 days",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )
    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        format="{message}"
    )

    logger.info(f"Starting Email Agent in {args.mode} mode")

    try:
        agent = EmailAgent()

        if args.mode == "once":
            agent.run_once()
        else:
            if args.interval:
                settings.check_interval_seconds = args.interval
                logger.info(f"Using custom interval: {args.interval}s")
            agent.run_continuously()

        agent.print_stats()

    except KeyboardInterrupt:
        logger.info("Email Agent stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in Email Agent: {e}")
        raise


if __name__ == "__main__":
    main()