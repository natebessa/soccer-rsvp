import os
from dotenv import load_dotenv
from flask import Flask, request

from .utils import (
    build_sms_message,
    generate_sms_reply_to_status,
    get_next_saturday_date,
    get_roster,
    log_message,
    save_rsvp,
    send_sms,
    update_player_active_flag
)


load_dotenv()
app = Flask(__name__)

TEAM_NAME = os.environ.get('TEAM_NAME')
EVENT_DATE = get_next_saturday_date()


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
    log_message(phone=phone, message=message, inbound=True)

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
        save_rsvp(player_name=roster[phone], status=message, date=EVENT_DATE)

        return build_sms_message(phone=phone, message="Thank you!\n\nYou can change your RSVP any time by sending another YES/NO.")

    # Process a status request.
    elif message == 'STATUS':
        return generate_sms_reply_to_status(phone=phone, date=EVENT_DATE)

    # Process requests to leave the league and stop receiving messages.
    elif message == 'LEAVE':
        update_player_active_flag(phone=phone, active=False)
        return build_sms_message(phone=phone, message=f"You're now unsubscribed from future {TEAM_NAME} messages. If you change your mind later, please reach out to Nate directly.")

    return "Error: Unsupported text message.", 500