import os
import requests
import subprocess

class Mail:
    def __init__(self):
        self.hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME', 'connectors.replit.com')

    def _get_auth_token(self):
        try:
            result = subprocess.run(
                ["replit", "identity", "create", "--audience", f"https://{self.hostname}"],
                capture_output=True, text=True, check=True
            )
            token = result.stdout.strip()
            if not token:
                raise Exception("Empty token received")
            return f"Bearer {token}"
        except Exception as e:
            print(f"Error getting Replit Identity Token: {e}")
            return None

    def send(self, to, subject, body, html=None, from_email=None):
        auth_token = self._get_auth_token()
        if not auth_token:
            print("Failed to send email: No authentication token")
            return False

        url = f"https://{self.hostname}/api/v2/mailer/send"
        headers = {
            "Content-Type": "application/json",
            "Replit-Authentication": auth_token
        }

        payload = {
            "to": to,
            "subject": subject,
            "text": body
        }
        if from_email:
            payload["from"] = from_email
        if html:
            payload["html"] = html

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if 200 <= response.status_code < 300:
                print(f"Email sent successfully to {to}")
                return True
            else:
                print(f"Failed to send email to {to}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Error sending email to {to}: {e}")
            return False
