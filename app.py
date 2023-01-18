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

EVENT_DATE = os.environ.get('EVENT_DATE')

def get_roster():
    """Returns the roster players."""
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

def get_rsvps(date):
    """Returns the RSVPs for a given date."""
    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_RSVPS')).execute()
    results = result.get('values', [])

    # Status:[Name]
    rsvps = {
        'YES': [],
        'NO': []
    }

    # Skip the header row.
    for rsvp in results[1:]:
        if rsvp[1] == EVENT_DATE:
            rsvps[rsvp[2]].append(rsvp[0])

    return rsvps

def log_message(phone, message, direction):
    """Writes what messages are sent/received to the appropriate spreadsheet."""

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

def get_sms_reply_twiml(phone, message):
    """Logs the message we'll send and returns a message ready for sending TwiML markup."""
    log_message(phone, message, 'outbound')
    response = MessagingResponse()
    response.message(message)
    return str(response)

def send_sms(phone, message):
    client.messages.create(
        body=message,
        from_=os.environ.get('TWILIO_PHONE_NUMBER'),
        to=phone
    )

    log_message(phone, message, 'outbound')

def get_sms_rsvp_summary_twiml(phone):
    """Returns the TwiML markup for a text with a summary of RSVPs so far for the next event."""
    rsvps = get_rsvps(date=EVENT_DATE)
    message = f"So far we have {len(rsvps['YES'])} YES and {len(rsvps['NO'])} NO.\n\n"
    message += f"Yes: {', '.join(rsvps['YES'])}\n\n"
    message += f"No: {', '.join(rsvps['NO'])}"
    return get_sms_reply_twiml(phone, message)

# Writes someone's RSVP to the spreadsheet.
def save_rsvp(phone, status):
    values = [[phone, EVENT_DATE, status.upper().strip()]]
    body = {'values': values}
    sheet.values().append(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                          range=os.environ.get('SPREADSHEET_RANGE_RSVPS'),
                          valueInputOption='RAW',
                          body=body).execute()


@app.route("/")
def root():
    """Index page."""
    return f"Next game: {EVENT_DATE}"


@app.route('/roster', methods=['GET'])
def roster():
    """Return the current roster of the pickup league."""
    roster = get_roster()
    if not roster:
        return "Roster not found", 400

    player_names = roster.values()
    return '<strong>Roster:</strong><br>- ' + '<br>- '.join(player_names)


@app.route('/status', methods=['GET'])
def status():
    """Return the RSVP statuses for next game."""
    rsvps = get_rsvps(date=EVENT_DATE)

    html = f"<p><strong>Yes ({len(rsvps['YES'])})</strong></p>"
    html += "<ul>"
    for rsvp in rsvps['YES']:
        html += f"<li>{rsvp}</li>"
    html += "</ul>"

    html += f"<p><strong>No ({len(rsvps['NO'])})</strong></p>"
    html += "<ul>"
    for rsvp in rsvps['NO']:
        html += f"<li>{rsvp}</li>"
    html += "</ul>"

    return html

@app.route('/send-rsvp', methods=['GET'])
def send_rsvp():
    """Sends RSVP requests."""
    roster = get_roster()
    if not roster:
        return "Roster not found", 400

    message = f"Hey RHSG! Roll call for soccer on {EVENT_DATE} at 8am.\n\nPlease reply YES/NO if you can make it.\n\nReply STATUS to see who has responded so far."
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
    if message.upper().strip() not in ['YES', 'NO', 'STATUS']:
        message = 'Error: Please respond with only YES, NO, or STATUS.'
        response = get_sms_reply_twiml(phone=phone, message=message)
        return str(response)

    # Process RSVPs
    if message.upper().strip() in ['YES', 'NO']:

        # Check if sender is in our roster.
        roster = get_roster()
        if phone not in roster.keys():
            message = 'Sorry, you are not in our roster.'
            response = get_sms_reply_twiml(phone=phone, message=message)
            return str(response)

        # Save RSVP to Google Sheet.
        save_rsvp(roster[phone], message)

        message = "Thank you!"
        response = get_sms_reply_twiml(phone=phone, message=message)
        return str(response)

    elif message.upper().strip() == 'STATUS':
        response = get_sms_rsvp_summary_twiml(phone)
        return str(response)

    return "Error: Unsupported text message.", 500