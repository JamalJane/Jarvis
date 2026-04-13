
import os
import sys
from jarvis.core.google_services import GoogleServices

def test_google_apis():
    print("--- Starting Google API Integration Test ---")
    gs = GoogleServices()
    
    if not gs.is_authenticated():
        print("Error: Google services not authenticated.")
        return

    # 1. Test Calendar
    print("\n[1] Testing Calendar (Listing upcoming events)...")
    try:
        events = gs.list_upcoming_events(max_results=3)
        if not events:
            print("No upcoming events found (this is normal if your calendar is empty).")
        else:
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                print(f"- {start}: {event['summary']}")
    except Exception as e:
        print(f"Calendar test failed: {e}")

    # 2. Test Docs
    print("\n[2] Testing Docs (Creating a test document)...")
    try:
        doc_title = "Jarvis API Test Doc"
        doc = gs.create_doc(doc_title)
        print(f"Success! Created doc with ID: {doc.get('documentId')}")
        print(f"View it at: https://docs.google.com/document/d/{doc.get('documentId')}/edit")
    except Exception as e:
        print(f"Docs test failed: {e}")

    # 3. Test Gmail
    print("\n[3] Testing Gmail (Sending a self-test email)...")
    try:
        # You can change this to your email to see it in your inbox
        test_email = "basheirkhalid2011@gmail.com" 
        gs.send_email(
            to=test_email,
            subject="Jarvis Google API Test",
            body="If you see this, the Google API integration is working perfectly!"
        )
        print(f"Email sent successfully to {test_email}!")
    except Exception as e:
        print(f"Gmail test failed: {e}")

    print("\n--- Google API Integration Test Complete ---")

if __name__ == "__main__":
    test_google_apis()
