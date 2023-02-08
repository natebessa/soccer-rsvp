# soccer-rsvp
For what feels like many years now, I've managed a pick-up soccer league for friends. Each week I round up enough people (10 usually being the ideal number) to have competitive games. In the winter we split the cost of renting a school gym so we can keep playing through the coldest months. As the organizer, I take on some risk being on the hook for the gym fees if I don't have enough people to split the costs.

Up until recently, I would create posts in a private Facebook group to ask who would be coming. That worked fine for a while but more recently many of us have moved on from Facebook. I looked around for better options, for simple ways to ask people for a yes or no if they would make it to our next game. What was clear to me is everyone has a phone number, everyone is acustomed to sending text messages, and most people respond to texts.

What I didn't find out there was a simple text messaging solution for managing RSVPs to events. That's what this Flask-based application attempts to solve. I'm not sure yet if it's useful for anyone else, but at least for me it has made my life a lot easier! And I think my soccer teammates appreciate the simplicity of being able to text a number "YES" and "STATUS" to lock in their spot for our next game and to see who else is coming.

## Goals

My goals with this project were two-fold:
1. Simplify managing a pick-up soccer league by making it easy for players to RSVP via SMS.
2. Keep costs as close to zero as possible because this is a no revenue project.

This application is still very much in MVP phase. Some features I'd like to add to it overtime are:

- Automating the weekly sending of RSVP requests.
- A waitlist feature, so our games aren't over-subscribed.
- Collecting payments when RSVPing, so people who take a spot on the roster are financially committed.

## Technologies

For this project, I use the following technologies:
- Twilio: For sending and receiving SMS messages.
- Flask: For processing of messages and connectivity to the database.
- Lambda: Spins up the Flask application only on-demand to keep costs extremely low.
- API Gateway: Exposes the Lambda-deployed Flask application publicly as an API.
- Google Sheets: Free database storage. Something I can pull up on my phone whenever I need a quick look at the data.

## Open source and feedback

If you find this app useful, please feel to use it! You can clone the repo as is and follow the installation steps below. You can contibute to the development of this repo by opening a PR, which I'll review when I can. Or, fork the repo and grow it as you wish.

I'm open to any feedback. Let me know what you think by emailing me at nate(at)bessa.io

## Getting started

### Google Sheet setup

First, create your Google Sheet that'll act as your database. You can clone my example here: https://docs.google.com/spreadsheets/d/1o5qf7vRcRmPSKx3SnmclB_tXotI6HecymYzZSxCJd5g/edit#gid=0

### Twilio setup

You'll next need to have a Twilio (or similar) account to have a phone number and mechanism for sending messages. I chose Twilio because of its popularity and affordability.

### Repo setup

Then clone this repo and create an `.env` file at the root directory with the following:

```
# Event management
EVENT_DATE=02/11/2023
TEAM_NAME=Real Madrid

# Twilio credentials
TWILIO_ACCOUNT_SID={your twilio account sid}
TWILIO_AUTH_TOKEN={your twilio auth token}
TWILIO_PHONE_NUMBER=+1{your twilio phone number}

# Google Sheet info
SPREADSHEET_ID={the digits after the /d/ in a Sheets URL}
SPREADSHEET_RANGE_ROSTER='Roster!A:C'
SPREADSHEET_RANGE_RSVPS='RSVPs!A:C'
SPREADSHEET_RANGE_SMS_LOGS_RECEIVED='SmsLogsReceived!A:C'
SPREADSHEET_RANGE_SMS_LOGS_SENT='SmsLogsSent!A:C'
```

With these commands, create a virtualenv to install the Python requirements.

```
python3 -m pip install --user --upgrade pip
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

You can run now Flask locally to test out some basic things. But unless you expose your local environment publicly (i.e. through a service like ngrok), it won't be accessible for Twilio.

### AWS and Serverless setup

I created an AWS account on the Free Tier and connected it to an account with Serverless.com. This makes deploying Lambda + API Gateway applications on AWS super easy.

- Create an account on Serverless.com
- In the Serverless console, create an app `soccer-rsvp`
- Go to working directory of your repo ~/
- Run command `npm i -g serverless && serverless --org=YOUR-ORG --app=soccer-rsvp --name=soccer-rsvp`

### Local development

To run your Flask Lambda app locally, you can run `serverless wsgi serve` which will fire up the Flask application on your machine.

### Deploying changes

To deploy to AWS, simply run `serverless deploy` or `serverless deploy function --function api`.

Once your application has been deployed for the first time to AWS, Serverless will inform you of the public URL to your API. You'll need to copy that URL into Twilio where it asks you for a consumer for their webhook.