"""
Google Services Integration
----------------------------
Manages OAuth2 authentication and provides authenticated service clients
for Gmail, Google Calendar, and Google Docs APIs.

Configuration is driven entirely by environment variables (already in .env):
  GOOGLE_CREDENTIALS_PATH  — path to the OAuth2 credentials JSON file
  GOOGLE_TOKEN_PATH        — path where the saved token will be written/read

On first run (or when the token expires) the module opens a browser window
for the user to grant consent, then caches the token for subsequent runs.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# OAuth2 scopes required by the three APIs
SCOPES = [
    # Gmail — send, read, compose
    "https://www.googleapis.com/auth/gmail.modify",
    # Google Calendar — full access
    "https://www.googleapis.com/auth/calendar",
    # Google Docs — read & write
    "https://www.googleapis.com/auth/documents",
    # Google Drive (needed for Docs file listing)
    "https://www.googleapis.com/auth/drive.file",
]


class GoogleServices:
    """
    Manages Google API authentication and provides service clients.

    Usage:
        gs = GoogleServices()
        gmail   = gs.get_gmail_service()
        calendar = gs.get_calendar_service()
        docs    = gs.get_docs_service()
    """

    def __init__(self):
        self._creds = None
        self._credentials_path = Path(
            os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        )
        self._token_path = Path(
            os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        )

        self._authenticate()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self):
        """Load existing token or run OAuth2 flow to obtain new credentials."""
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request

            creds: Optional[Credentials] = None

            # Load an existing token if available
            if self._token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(self._token_path), SCOPES
                )
                logger.info(f"Loaded Google token from {self._token_path}")

            # Refresh expired token automatically
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Google token refreshed successfully")
                except Exception as e:
                    logger.warning(f"Token refresh failed, re-authorising: {e}")
                    creds = None

            # First-time (or re-auth) flow — opens browser for user consent
            if not creds or not creds.valid:
                if not self._credentials_path.exists():
                    raise FileNotFoundError(
                        f"Google credentials file not found: {self._credentials_path}. "
                        "Download it from https://console.cloud.google.com/apis/credentials "
                        "and set GOOGLE_CREDENTIALS_PATH in your .env file."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("Google OAuth2 authorization completed")

            # Persist the token so we don't need to re-auth every run
            self._token_path.write_text(creds.to_json())
            logger.info(f"Google token saved to {self._token_path}")

            self._creds = creds

        except ImportError as e:
            logger.error(
                f"Google API libraries not installed: {e}. "
                "Run: pip install google-api-python-client google-auth-httplib2 "
                "google-auth-oauthlib google-auth"
            )
            self._creds = None
        except Exception as e:
            logger.error(f"Google authentication failed: {e}")
            self._creds = None

    # ------------------------------------------------------------------
    # Service getters
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        """Returns True if OAuth credentials are valid and ready."""
        return self._creds is not None and self._creds.valid

    def get_gmail_service(self):
        """
        Returns an authenticated Gmail API service client.

        Example:
            service = gs.get_gmail_service()
            result = service.users().messages().list(userId='me').execute()
        """
        if not self._creds:
            raise RuntimeError("Google credentials not available – check logs for auth errors.")
        from googleapiclient.discovery import build
        return build("gmail", "v1", credentials=self._creds)

    def get_calendar_service(self):
        """
        Returns an authenticated Google Calendar API service client.

        Example:
            service = gs.get_calendar_service()
            events = service.events().list(calendarId='primary').execute()
        """
        if not self._creds:
            raise RuntimeError("Google credentials not available – check logs for auth errors.")
        from googleapiclient.discovery import build
        return build("calendar", "v3", credentials=self._creds)

    def get_docs_service(self):
        """
        Returns an authenticated Google Docs API service client.

        Example:
            service = gs.get_docs_service()
            doc = service.documents().get(documentId='...').execute()
        """
        if not self._creds:
            raise RuntimeError("Google credentials not available – check logs for auth errors.")
        from googleapiclient.discovery import build
        return build("docs", "v1", credentials=self._creds)

    def get_drive_service(self):
        """
        Returns an authenticated Google Drive API service client.
        Useful for searching/listing Docs files.

        Example:
            service = gs.get_drive_service()
            files = service.files().list(q="mimeType='application/vnd.google-apps.document'").execute()
        """
        if not self._creds:
            raise RuntimeError("Google credentials not available – check logs for auth errors.")
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=self._creds)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def send_email(self, to: str, subject: str, body: str) -> dict:
        """Send a plain-text email via Gmail. Returns message dict with 'id'."""
        import base64
        from email.mime.text import MIMEText

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service = self.get_gmail_service()
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        logger.info(f"Email sent to {to}, message id: {result.get('id')}")
        return result

    def list_recent_emails(self, max_results: int = 10, query: str = "") -> list:
        """
        List recent emails from Gmail inbox.

        Args:
            max_results: How many messages to return (default 10)
            query:       Optional Gmail search string, e.g. 'is:unread' or 'from:boss@co.com'

        Returns:
            List of dicts: {id, subject, from, date, snippet}
        """
        service = self.get_gmail_service()
        list_kwargs = {"userId": "me", "maxResults": max_results, "labelIds": ["INBOX"]}
        if query:
            list_kwargs["q"] = query

        resp = service.users().messages().list(**list_kwargs).execute()
        messages = resp.get("messages", [])

        results = []
        for msg in messages:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            results.append({
                "id":      msg["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "from":    headers.get("From", ""),
                "date":    headers.get("Date", ""),
                "snippet": detail.get("snippet", ""),
            })

        logger.info(f"Fetched {len(results)} emails")
        return results

    def list_upcoming_events(self, max_results: int = 10) -> list:
        """Fetch the next N upcoming Google Calendar events."""
        import datetime

        now = datetime.datetime.utcnow().isoformat() + "Z"
        service = self.get_calendar_service()
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        logger.info(f"Fetched {len(events)} upcoming calendar events")
        return events

    def create_doc(self, title: str) -> dict:
        """Create a new Google Doc. Returns doc resource dict with 'documentId'."""
        service = self.get_docs_service()
        doc = service.documents().create(body={"title": title}).execute()
        logger.info(f"Created Google Doc: {doc.get('documentId')} -- '{title}'")
        return doc
