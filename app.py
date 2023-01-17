from datetime import datetime
import os

from dotenv import load_dotenv
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from apiclient import discovery
from google.oauth2 import service_account

load_dotenv()
app = Flask(__name__)

# Twilio setup.
client = Client(os.environ.get('TWILIO_ACCOUNT_SID'), os.environ.get('TWILIO_AUTH_TOKEN'))

# Google Sheets setup.
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
GOOGLE_SECRETS_FILE = 'google-creds.json'
secret_file = os.path.join(os.getcwd(), GOOGLE_SECRETS_FILE)
credentials = service_account.Credentials.from_service_account_file(secret_file, scopes=GOOGLE_SCOPES)
service = discovery.build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()


# Pulls the roster list from the spreadsheet.
def get_roster():
    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_ROSTER')).execute()
    return result.get('values', [])


# Writes someone's RSVP to the spreadsheet.
def save_rsvp(name, status):
    values = [[name, os.environ.get('EVENT_DATE'), status]]
    body = {'values': values}
    sheet.values().append(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                          range=os.environ.get('SPREADSHEET_RANGE_RSVPS'),
                          valueInputOption='RAW',
                          body=body).execute()


@app.route("/")
def root():
    """Index page."""
    return f"Next game: {os.environ.get('EVENT_DATE')}"


@app.route('/roster', methods=['GET'])
def roster():
    """Return the current roster of the pickup league."""
    roster = get_roster()
    if not roster:
        return "Roster not found", 400

    player_names = [player[0] for player in roster[1:] if player[2] == 'Yes']
    return '<strong>Roster:</strong><br>- ' + '<br>- '.join(player_names)


@app.route('/twilio', methods=['POST'])
def twilio():
    """The webhook for Twilio. This processes SMS messages sent by players
    and stores their RSVP to our database."""

    # Strip plus signs from phone numbers.
    user_phone = request.values.get('From', '').replace('+', '')
    message = request.values.get('Body', '')

    if message.upper() not in ['YES', 'NO']:
        message = client.messages.create(
            body='Error: Please respond with only a YES or NO.',
            from_=os.environ.get('TWILIO_PHONE_NUMBER'),
            to=user_phone
        )
        return "Error: Invalid SMS body", 400

    # Check if sender is in our roster.
    roster = get_roster()
    allowed_phone_numbers = [player[1] for player in roster[1:]]
    if user_phone not in allowed_phone_numbers:
        message = client.messages.create(
            body='Sorry, you are not in our roster.',
            from_=os.environ.get('TWILIO_PHONE_NUMBER'),
            to=user_phone
        )
        return "Error: Sender not in roster", 403

    # Save RSVP to Google Sheet.
    save_rsvp(user_phone, message)

    message = client.messages.create(
        body='Thank you!',
        from_=os.environ.get('TWILIO_PHONE_NUMBER'),
        to=user_phone
    )
    return "Success", 200
