# soccer-rsvp
 An app to simplify and automate managing pickup soccer attendance.

## Goals

My goals with this project are to:
- Learn more about NextJS, React, Twilio, and Serverless applications
- Keep costs as close to zero as possible because this is a no revenue project
- Simplify managing a pick-up soccer league by making it easy for players to RSVP via SMS

## Architecture

Lambda -> Twilio -> API Gateway -> Lambda -> Google Sheet

## Serverless setup

To simplify deploying this project, I used Serverless. Here's how to set things up:

- Create an account on Serverless.com
- In the Serverless console, create an app `soccer-rsvp`
- Go to working directory ~/
- Run command `npm i -g serverless && serverless --org=YOUR-ORG --app=soccer-rsvp --name=soccer-rsvp`

## Local Development

With these commands, I create a virtualenv to install my python requirements and I use serverless to stand up the flask app locally.

```
python3 -m pip install --user --upgrade pip
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
serverless wsgi serve
```

# Deploying

Serverless uses Cloudformation to deploy this project. Whenever you're ready to deploy for the first time and afterward with any changes, just run `serverless deploy`.