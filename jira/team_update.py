from apiclient import discovery
from apiclient import errors
import argparse
import base64
from collections import defaultdict
from collections import OrderedDict
import datetime
from email.mime.text import MIMEText
import httplib2
from jinja2 import Template
from jira import JIRA
import oauth2client
from oauth2client import client
from oauth2client import tools
import os
import requests


JIRA_URL = ''
JIRA_PROJECT = ''
JIRA_CONSUMER_KEY = ''
JIRA_KEY_CERT = ''
JIRA_ACCESS_TOKEN = ''
JIRA_ACCESS_TOKEN_SECRET = ''
JIRA_COMPONENTS = [  # Wrap strings in double quotes
    '"Backend"',
    '"Query API"',
    '"Import"',
    '"Frontend"'
]

SCOPES = 'https://www.googleapis.com/auth/gmail.compose'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'team-update'

FROM = ''
TO = ''
TEAM = ''

email_template = '''
{% macro format_jira_key(issue) %}
    <a href="https://interana.atlassian.net/browse/{{ issue }}">{{ issue }}</a>
{% endmacro %}
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN">
<html lang="en">
<body>
    {% for sprint, tickets in jira_info.iteritems() %}
        <h4>{{ sprint }}</h4>
        <p>Done:</p>
        {% if tickets.completed %}
        <ul>
        {% for ticket, summary in tickets.completed.iteritems() %}
            <li>{{ format_jira_key(ticket) }}: {{ summary }}</li>
        {% endfor %}
        </ul>
        {% endif %}
        <p>In Progress:</p>
        {% if tickets.in_progress %}
        <ul>
        {% for ticket, summary in tickets.in_progress.iteritems() %}
            <li>{{ format_jira_key(ticket) }}: {{ summary }}</li>
        {% endfor %}
        </ul>
        {% endif %}
    {% endfor %}
</body>
</html>
'''


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir, 'team-updates.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
        credentials = tools.run_flow(flow, store, flags)
        print 'Storing credentials to ' + credential_path
    return credentials


def get_jira_info():
    print("\nGetting JIRA info...")
    jira = create_jira_client()

    base_query = (
        'project = {project} and Sprint in openSprints() '
        'and component in ({components})'
    ).format(
        project=JIRA_PROJECT,
        components=", ".join(JIRA_COMPONENTS)
    )

    query = base_query + ' and status in ("In Progress", "In Review")'
    in_progress_issues = jira.search_issues(query)

    query = base_query + (
        ' and status in (Resolved, Closed)'
        ' and resolutiondate > -7d'
    )
    completed_issues = jira.search_issues(query)

    return sort_by_sprint(in_progress_issues, completed_issues)


def create_jira_client():
    key_cert_data = None
    with open(JIRA_KEY_CERT, 'r') as key_cert_file:
        key_cert_data = key_cert_file.read()

    oauth_dict = {
        'access_token': JIRA_ACCESS_TOKEN,
        'access_token_secret': JIRA_ACCESS_TOKEN_SECRET,
        'consumer_key': JIRA_CONSUMER_KEY,
        'key_cert': key_cert_data
    }
    return JIRA(JIRA_URL, oauth=oauth_dict)


def sort_by_sprint(in_progress_issues, completed_issues):
    sorted = defaultdict(lambda: dict(
            in_progress=OrderedDict(),
            completed=OrderedDict()
        ))
    for issue in in_progress_issues:
        sorted[get_sprint(issue)]['in_progress'][issue.key] = issue.fields.summary
    for issue in completed_issues:
        sorted[get_sprint(issue)]['completed'][issue.key] = issue.fields.summary
    return sorted        


def get_sprint(issue):
    # assumes an issue can only be in 1 active sprint
    sprints = issue.fields.customfield_10007
    for sprint in sprints:
        attrs = sprint.split(',')
        status = attrs[2].split('=')[1]
        name = attrs[3].split('=')[1]
        if status == 'ACTIVE':
            return name
    return ""  # don't break in unexpected case of no active sprints


def CreateMessage(sender, to, subject, message_text):
    """Create a message for an email.

    Args:
        sender: Email address of the sender.
        to: Email address of the receiver.
        subject: The subject of the email message.
        message_text: The text of the email message.

    Returns:
        An object containing a base64url encoded email object.
    """
    message = MIMEText(message_text, 'html', 'utf-8')
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(message.as_string())}


def CreateDraft(service, user_id, message_body):
    """Create and insert a draft email. Print the returned draft's message and id.

    Args:
        service: Authorized Gmail API service instance.
        user_id: User's email address. The special value "me"
        can be used to indicate the authenticated user.
        message_body: The body of the email message, including headers.

    Returns:
        Draft object, including draft id and message meta data.
    """
    try:
        message = {'message': message_body}
        draft = service.users().drafts().create(
            userId=user_id, 
            body=message
        ).execute()

        print '\nDraft id: {id}\nDraft message: {message}'.format(
            id=draft['id'], 
            message=draft['message']
        )
        return draft
    except errors.HttpError, error:
        print 'An error occurred: %s' % error
        return None


def main(args=None):
    print("Creating weekly team update email")

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('gmail', 'v1', http=http)

    subject = "{team_name} team update".format(team_name=TEAM)

    template = Template(email_template)
    message_text = template.render(
        jira_info=get_jira_info()
    )

    message = CreateMessage(
        FROM, 
        TO,
        subject, 
        message_text
    )
    CreateDraft(service, 'me', message)

    print("\nFinished generating email")


if __name__ == '__main__':
    main()
