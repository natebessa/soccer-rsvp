import datetime
import os
import pytz
from dotenv import load_dotenv
from typing import Dict, Optional, Set

# Google imports
from apiclient import discovery
from google.oauth2 import service_account

# Twilio imports
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

# Twilio setup.
client = Client(os.environ.get('TWILIO_ACCOUNT_SID'), os.environ.get('TWILIO_AUTH_TOKEN'))

# Google Sheets setup.
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
GOOGLE_SECRETS_FILE = 'google-creds.json'
secret_file = os.path.join(os.getcwd(), GOOGLE_SECRETS_FILE)
credentials = service_account.Credentials.from_service_account_file(secret_file, scopes=GOOGLE_SCOPES)
service = discovery.build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()


def get_next_saturday_date() -> str:
    """Our games are played on Saturdays. Return the next Saturday date."""

    eastern_tz = pytz.timezone("US/Eastern")
    today = datetime.datetime.now(eastern_tz)
    days_until_saturday = 5 - today.weekday()

    if days_until_saturday == 0:
        return today.date().strftime("%m/%d/%Y")

    if days_until_saturday < 0:
        days_until_saturday += 7

    date = today + datetime.timedelta(days=days_until_saturday)
    return date.strftime("%m/%d/%Y")

def get_roster() -> Dict[str, str]:
    """Returns the roster of players as a dict of phone:name pairs."""

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

def get_roster_row_number(phone: str) -> Optional[int]:
    """Returns the row number in the Roster spreadsheet with the given phone
    number, or None if not found."""

    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_ROSTER')).execute()

    results = result.get('values', [])

    # Google Sheets A1 notation uses a 1-index.
    for row_num, row in enumerate(results, 1):
        if row[1] == phone:
            return row_num

    return None

def get_rsvps(date: str) -> Dict[str, Set[str]]:
    """Returns the RSVPs for a given date as a dict of status:set(player names) pairs."""

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
        if rsvp[1] == date:
            rsvps[rsvp[2]].add(rsvp[0])

    return rsvps

def get_rsvp_row_number(player_name: str, date: str) -> Optional[int]:
    """Returns the row number in the RSVPs spreadsheet with the given player name
    and date pairing, or None if not found."""

    result = sheet.values().get(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                range=os.environ.get('SPREADSHEET_RANGE_RSVPS')).execute()

    results = result.get('values', [])

    # Google Sheets A1 notation uses a 1-index.
    for row_num, row in enumerate(results, 1):
        if row[0] == player_name and row[1] == date:
            return row_num

    return None

def log_message(phone: str, message: str, inbound: bool):
    """Logs messages sent/received to the appropriate spreadsheet."""

    values = [[phone, datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S"), message]]
    body = {'values': values}

    if inbound:
        spreadsheet = os.environ.get('SPREADSHEET_RANGE_SMS_LOGS_RECEIVED')
    else:
        spreadsheet = os.environ.get('SPREADSHEET_RANGE_SMS_LOGS_SENT')

    sheet.values().append(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                          range=spreadsheet,
                          valueInputOption='RAW',
                          body=body).execute()

def build_sms_message(phone:str , message: str) -> str:
    """Logs the message we'll send and returns a message ready for sending with TwiML markup."""

    log_message(phone=phone, message=message, inbound=False)
    response = MessagingResponse()
    response.message(message)
    return str(response)

def generate_sms_reply_to_status(phone: str, date: str) -> str:
    """Returns the TwiML markup for a text with a summary of RSVPs so far for the next event."""

    rsvps = get_rsvps(date=date)
    message = f"For {date}, so far we have {len(rsvps['YES'])} YES and {len(rsvps['NO'])} NO.\n\n"
    message += f"Yes: {', '.join(sorted(rsvps['YES']))}\n\n"
    message += f"No: {', '.join(sorted(rsvps['NO']))}"
    return build_sms_message(phone=phone, message=message)

def send_sms(phone: str, message: str):
    """Sends a message with Twilio and save a log of it."""

    client.messages.create(
        body=message,
        from_=os.environ.get('TWILIO_PHONE_NUMBER'),
        to=phone
    )

    log_message(phone=phone, message=message, inbound=False)

def save_rsvp(player_name: str, status: str, date: str):
    """Write to the spreadsheet the player and their RSVP for the given date."""

    # Check to see if player already has RSVPed.
    existing_rsvp_row = get_rsvp_row_number(player_name=player_name, date=date)

    values = [[player_name, date, status]]
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

def update_player_active_flag(phone: str, active: str):
    """Updates a player's Active flag in the spreadsheet."""

    existing_roster_row = get_roster_row_number(phone=phone)

    if existing_roster_row:
        values = [['Yes' if active else 'No']]
        body = {'values': values}
        request = sheet.values().update(spreadsheetId=os.environ.get('SPREADSHEET_ID'),
                                        range=f'Roster!C{existing_roster_row}', # Google Sheets A1 Notation
                                        valueInputOption='RAW',
                                        body=body)
        request.execute()
