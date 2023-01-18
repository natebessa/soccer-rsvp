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
    """Returns a list of tuples of roster players. Can filter out players
    by active status and if they're beta testers."""
    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_ROSTER')).execute()
    results = result.get('values', [])

    # Phone:name dict
    players = {}

    # Skip the header row.
    for player in results[1:]:
        if player[2] == 'Yes' and player[3] == 'Yes':
            # Remove unicode characters that sometimes come in through the spreadsheet.
            phone_encoded = player[1].encode("ascii", "ignore")
            phone_decoded = phone_encoded.decode()
            players[phone_decoded] = player[0]

    return players

# Writes what messages are sent/received to the appropriate spreadsheet.
def log_message(phone, message, direction):
    values = [[phone, datetime.now().strftime("%m/%d/%Y, %H:%M:%S"), message]]
    body = {'values': values}

    if direction == 'inbound':
        spreadsheet = os.environ.get('SPREADSHEET_RANGE_SMS_LOGS_RECEIVED')
    elif direction == 'outbound':
        spreadsheet = os.environ.get('SPREADSHEET_RANGE_SMS_LOGS_SENT')
    else:
        raise Exception('Direction unknown')

    sheet.values().append(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                          range=spreadsheet,
                          valueInputOption='RAW',
                          body=body).execute()

def send_sms(phone, message):
    client.messages.create(
        body=message,
        from_=os.environ.get('TWILIO_PHONE_NUMBER'),
        to=phone
    )

    log_message(phone, message, 'outbound')

# Writes someone's RSVP to the spreadsheet.
def save_rsvp(phone, status):
    values = [[phone, os.environ.get('EVENT_DATE'), status.upper()]]
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

    player_names = roster.values()
    return '<strong>Roster:</strong><br>- ' + '<br>- '.join(player_names)


@app.route('/send-rsvp', methods=['GET'])
def send_rsvp():
    """Sends RSVP requests."""
    roster = get_roster()
    if not roster:
        return "Roster not found", 400

    message = f"Hey RHSG! Please reply YES/NO if you'll be at soccer on {os.environ.get('EVENT_DATE')} at 8am. -Nate"
    for phone in roster.keys():
        send_sms(phone, message)

    return f"Messages sent to {len(roster)} people"


@app.route('/twilio', methods=['POST'])
def twilio():
    """The webhook for Twilio. This processes SMS messages sent by players
    and stores their RSVP to our database."""

    # Strip plus signs from phone numbers.
    phone = request.values.get('From', '').replace('+', '')
    message = request.values.get('Body', '')

    # Log all responses for debugging.
    log_message(phone, message, 'inbound')

    # Remove trailing white spaces that some iPhones add.
    if message.upper().strip() not in ['YES', 'NO']:
        error_message = 'Error: Please respond with only a YES or NO.'
        send_sms(phone, error_message)
        return "Error: Invalid SMS body", 400

    # Check if sender is in our roster.
    roster = get_roster()
    if phone not in roster.keys():
        error_message = 'Sorry, you are not in our roster.'
        send_sms(phone, error_message)
        return "Error: Sender not in roster", 403

    # Save RSVP to Google Sheet.
    save_rsvp(roster[phone], message)

    success_message = "Thank you!"
    send_sms(phone, success_message)

    return "Success", 200
