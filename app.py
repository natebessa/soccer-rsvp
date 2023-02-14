import datetime
import os
import pytz

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

TEAM_NAME = os.environ.get('TEAM_NAME')

def get_next_saturday_date():
    """Games are played on Saturdays. Return the next Saturday date."""

    eastern_tz = pytz.timezone("US/Eastern")
    today = datetime.datetime.now(eastern_tz)
    days_until_saturday = 5 - today.weekday()

    if days_until_saturday == 0:
        return today.date()
    elif days_until_saturday < 0:
        days_until_saturday += 7

    next_saturday = today + datetime.timedelta(days=days_until_saturday)
    return next_saturday.date().strftime("%m/%d/%Y")

EVENT_DATE = get_next_saturday_date()

def get_roster():
    """Returns the roster players."""

    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_ROSTER')).execute()

    results = result.get('values', [])

    # Phone:name dict
    players = {}

    # Skip the header row.
    for player in results[1:]:
        # "Active" column
        if player[2] == 'Yes':
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
        'YES': set(),
        'NO': set()
    }

    # Skip the header row.
    for rsvp in results[1:]:
        if rsvp[1] == EVENT_DATE:
            rsvps[rsvp[2]].add(rsvp[0])

    return rsvps

def get_rsvp_row_number(player_name, date):
    """To assist with updating existing records, scan the spreadsheet
    to see if there is already a row with this player and date. Return
    the row number if so."""

    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_RSVPS')).execute()

    results = result.get('values', [])

    # Google Sheets A1 notation uses a 1-index.
    for row_num, row in enumerate(results, 1):
        if row[0] == player_name and row[1] == date:
            return row_num

    return None

def get_roster_row_number(phone):
    """To assist with updating existing records, scan the spreadsheet
    to see if there is already a row with this player. Return the row
    number if so."""

    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_ROSTER')).execute()

    results = result.get('values', [])

    # Google Sheets A1 notation uses a 1-index.
    for row_num, row in enumerate(results, 1):
        if row[1] == phone:
            return row_num

    return None

def log_message(phone, message, direction):
    """Writes what messages are sent/received to the appropriate spreadsheet."""

    values = [[phone, datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S"), message]]
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

def build_sms_message(phone, message):
    """Logs the message we'll send and returns a message ready for sending TwiML markup."""
    log_message(phone=phone, message=message, direction='outbound')
    response = MessagingResponse()
    response.message(message)
    return str(response)

def generate_sms_reply_to_status(phone):
    """Returns the TwiML markup for a text with a summary of RSVPs so far for the next event."""
    rsvps = get_rsvps(date=EVENT_DATE)
    message = f"For {EVENT_DATE}, so far we have {len(rsvps['YES'])} YES and {len(rsvps['NO'])} NO.\n\n"
    message += f"Yes: {', '.join(sorted(rsvps['YES']))}\n\n"
    message += f"No: {', '.join(sorted(rsvps['NO']))}"
    return build_sms_message(phone=phone, message=message)

def send_sms(phone, message):
    client.messages.create(
        body=message,
        from_=os.environ.get('TWILIO_PHONE_NUMBER'),
        to=phone
    )

    log_message(phone, message, 'outbound')

# Writes someone's RSVP to the spreadsheet.
def save_rsvp(player_name, status):

    # Check to see if player already has RSVPed.
    existing_rsvp_row = get_rsvp_row_number(player_name=player_name, date=EVENT_DATE)

    values = [[player_name, EVENT_DATE, status]]
    body = {'values': values}

    if existing_rsvp_row:
        request = sheet.values().update(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                        range=f'RSVPs!A{existing_rsvp_row}:C{existing_rsvp_row}', # Google Sheets A1 Notation
                                        valueInputOption='RAW',
                                        body=body)
        request.execute()
    else:
        sheet.values().append(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                              range=os.environ.get('SPREADSHEET_RANGE_RSVPS'),
                              valueInputOption='RAW',
                              body=body).execute()

# Updates a player's "active" status in the roster.
def update_player_active_flag(phone, active):

    existing_roster_row = get_roster_row_number(phone=phone)
    active_flag = 'Yes' if active else 'No'

    values = [[active_flag]]
    body = {'values': values}

    if existing_roster_row:
        request = sheet.values().update(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                        range=f'Roster!C{existing_roster_row}', # Google Sheets A1 Notation
                                        valueInputOption='RAW',
                                        body=body)
        request.execute()


@app.route('/send-rsvp', methods=['GET'])
def send_rsvp():
    """Triggers the sending of RSVP requests. This endpoint should
    eventually be replaced by an automated process that triggers SMS
    RSVP requests."""

    roster = get_roster()
    message = f"Hey {TEAM_NAME}! Roll call for soccer on {EVENT_DATE} at 8am.\n\nPlease reply YES/NO if you can make it.\n\nYou can also reply STATUS to see responses so far. Text LEAVE if you want to stop receiving these messages."
    for phone in roster.keys():
        send_sms(phone, message)

    return f"Messages sent to {len(roster)} people"


@app.route('/twilio', methods=['POST'])
def twilio():
    """The consumer for the Twilio webhook. Processes messages sent by players
    and stores their RSVP in the database."""

    # Strip plus signs from phone numbers.
    phone = request.values.get('From', '').replace('+', '')
    message = request.values.get('Body', '')

    # Log all responses for debugging.
    log_message(phone=phone, message=message, direction='inbound')

    # Remove any white spaces and capitalize.
    message = message.upper().strip()

    # Validate sender.
    roster = get_roster()
    if phone not in roster.keys():
        message = "Sorry, you are not in our roster."
        return build_sms_message(phone=phone, message=message)

    # Validate message.
    allowed_responses = ['YES', 'NO', 'STATUS', 'LEAVE']
    if message not in allowed_responses:
        message = f"Sorry, I am a dumb bot. The only responses I understand at this time are: {', '.join(allowed_responses)}."
        return build_sms_message(phone=phone, message=message)

    # Process RSVPs.
    if message in ['YES', 'NO']:

        # Save RSVP to Google Sheet.
        save_rsvp(player_name=roster[phone], status=message)

        return build_sms_message(phone=phone, message="Thank you!\n\nYou can change your RSVP any time by sending another YES/NO.")

    # Process a status request.
    elif message == 'STATUS':
        return generate_sms_reply_to_status(phone=phone)

    # Process requests to leave the league and stop receiving messages.
    elif message == 'LEAVE':
        update_player_active_flag(phone=phone, active=False)
        return build_sms_message(phone=phone, message=f"You're now unsubscribed from future {TEAM_NAME} messages. If you change your mind later, please reach out to Nate directly.")

    return "Error: Unsupported text message.", 500