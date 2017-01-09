import argparse
from collections import defaultdict, namedtuple, OrderedDict
import datetime
from dateutil import parser
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader, Template
from jira import JIRA
import smtplib


JIRA_URL = ''
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

SMTP_USER = ''
SMTP_PASS = ''

# Changes won't be included
CHANGELOG_BLACKLIST = [
    'Story Points',
    'Rank',
    'Sprint',
    'RemoteIssueLink',
    'Attachment',
    'Epic Color',
    'Epic Child',
    'Resolved By'
]
# Changes will be merged into one entry
CHANGELOG_CONSOLIDATE = [
    'Component',
    'Version',
    'Fix Version'
]
# Only the latest change will be included
CHANGELOG_TRUNCATE = [
    'Status',
    'Priority',
    'Description',
    'Summary'
]


Issue = namedtuple('Issue', ['key', 'summary', 'type', 'priority', 'status'])
Summary = namedtuple('Summary', ['field', 'author', 'fromStr', 'toStr'])


def main(args=None):
    print('Creating Jira Digest email')

    args = parse_args()
    jql_query = create_jql_query(args)
    issues = search_issues(jql_query)
    issues_to_summaries = get_issue_summaries(issues, args)

    if issues_to_summaries:
        message = generate_message(issues_to_summaries, args)
        send_email(message, args)
        print('\nSent Jira Digest')
    else:
        print('\nNo changes to report')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Send a JIRA digest email summarizing recent changes.'
    )
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='summary period in hours preceding now (default: 24)'
    )
    parser.add_argument(
        '--email',
        default='amuller@interana.com',
        help='email address to send summary'
    )
    parser.add_argument(
        '--user',
        default='amuller',
        help='jira user to summarize'
    )
    # TODO: Add start_time and end_time flags
    return parser.parse_args()


def create_jql_query(args):
    '''
    Constructs a JQL query using the user and hours parameters
    from the args parameter. The query searches for relevant issues
    created in the last X hours, or updated in the last X hours
    where the issue is assigned or watched by the user.
    '''
    jql_query = (
        'project = HIG and ((component in ({components}) and created >= -{hours}h) '
        'or ((watcher = {user} or assignee = {user}) and updated >= -{hours}h))'
    ).format(
        components=", ".join(JIRA_COMPONENTS),
        hours=args.hours,
        user=args.user
    )
    return jql_query


def search_issues(jql_query):
    '''Issues a query to JIRA using the provided JQL query string
    '''
    print('\nIssuing JIRA query: {}'.format(jql_query))
    jira = create_jira_client()

    fields = 'summary, created, comment, issuetype, assignee, priority, status, reporter'
    issues = jira.search_issues(
        jql_query,
        fields=fields,
        expand='changelog',
        maxResults=100
    )
    return issues


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


def get_issue_summaries(issues, args):
    '''Returns a map of Issue tuples to a list of Summary tuples
    '''
    issues_to_summaries = defaultdict(list)
    for issue in issues:
        issue_tuple = Issue(
            key=issue.key,
            summary=issue.fields.summary,
            type=issue.fields.issuetype.name,
            priority=issue.fields.priority.name,
            status=issue.fields.status.name
        )
        add_created(issues_to_summaries, issue, issue_tuple, args)
        add_changelog(issues_to_summaries, issue, issue_tuple, args)
        add_comments(issues_to_summaries, issue, issue_tuple, args)

    sort_summaries(issues_to_summaries)
    return OrderedDict(sorted(issues_to_summaries.items(), key=lambda t: t[0].key))


def add_created(issues_to_summaries, issue, issue_tuple, args):
    '''
    Adds a summary entry to the dictionary if the issue was
    created in the time window by someone other than the user
    '''
    if (happened_in_time_window(issue.fields.created, args.hours) 
    and not_user(issue.fields.reporter, args.user)):
        issues_to_summaries[issue_tuple].append(
            Summary(
                field='Issue Created',
                author=issue.fields.reporter.displayName,
                fromStr="",
                toStr=""
            )
        )


def add_changelog(issues_to_summaries, issue, issue_tuple, args):
    '''
    Adds a summary entry to the dictionary for each entry in the
    issue's changelog if the change happened in the time window
    and was caused by someone other than the user
    '''
    history = issue.changelog.histories
    for entry in history:
        if (happened_in_time_window(entry.created, args.hours) 
        and not_user(entry.author, args.user)):
            summaries = create_summaries(entry)
            if summaries:  # avoid inserting empty list into dict
                issues_to_summaries[issue_tuple].extend(summaries)


def add_comments(issues_to_summaries, issue, issue_tuple, args):
    '''
    Adds a summary entry to the dictionary for each comment on the
    issue if the comment was created or updated in the time window
    and was created by someone other than the user
    '''
    for comment in issue.fields.comment.comments:
        if ((happened_in_time_window(comment.created, args.hours)
        or happened_in_time_window(comment.updated, args.hours)) 
        and not_user(comment.author, args.user)):
            issues_to_summaries[issue_tuple].append(
                Summary(
                    field='Comment',
                    author=comment.author.displayName,
                    fromStr="",
                    toStr=truncate(comment.body)
                )
            )


def happened_in_time_window(date_string, hours_back):
    '''
    Determines if the provided date_string occurred in the
    past hours_back hours
    '''
    parsed = parser.parse(date_string)
    now = datetime.datetime.utcnow()
    now = now.replace(tzinfo=parsed.tzinfo)
    delta = now - parsed
    return delta.total_seconds() <= (hours_back * 3600)


def not_user(jira_user, user):
    return user != jira_user.key and user != jira_user.name


def create_summaries(entry):
    '''
    Creates a list of Summary tuples for each item in the
    history entry, if the changed field is not in the blacklist
    '''
    return [
        Summary(
            field=item.field.title(),
            author=entry.author.displayName,
            fromStr=truncate(item.fromString),
            toStr=truncate(item.toString)
        ) for item in entry.items if item.field not in CHANGELOG_BLACKLIST
    ]


def truncate(string):
    '''Truncates the provided string to 140 characters
    '''
    if string and len(string) > 140:
        return string[:140] + '...'
    return string


def sort_summaries(issues_to_summaries):
    '''
    Updates each list of summaries in the dict as follows:
     * Issue Created summaries go first, all other summaries follow alphabetically
     * Summary fields in the CHANGELOG_CONSOLIDATE list are merged into one entry
     * Summary fields in the CHANGELOG_TRUNCATE list are removed, except for the
       last entry
    '''
    for issue, summaries in issues_to_summaries.items():
        sorted_summaries = []

        consolidated_summary = []
        alphabetical_summaries = sorted(summaries, key=lambda t: t.field)
        for index, summary in enumerate(alphabetical_summaries):
            # Put Issue Created first
            if summary.field == 'Issue Created':
                sorted_summaries.insert(0, summary)
            # Concatenate fields in CHANGELOG_CONSOLIDATE
            elif summary.field in CHANGELOG_CONSOLIDATE:
                if summary.toStr:  # this can be empty for some fields
                    consolidated_summary.append(summary.toStr)
                if not next_field_equals_current(alphabetical_summaries, index):
                    sorted_summaries.append(
                        Summary(
                            field=summary.field,
                            author=summary.author,
                            fromStr='',
                            toStr=', '.join(consolidated_summary)
                        )
                    )
                    consolidated_summary = []
            # Only add the last summary for fields in CHANGELOG_TRUNCATE
            elif summary.field in CHANGELOG_TRUNCATE:
                if not next_field_equals_current(alphabetical_summaries, index):
                    sorted_summaries.append(summary)
            # All other fields are included in order
            else:
                sorted_summaries.append(summary)

        issues_to_summaries[issue] = sorted_summaries


def next_field_equals_current(summaries, i):
    '''
    Determines if the Summary tuples in the list of summaries have 
    the same field at indexes i and i + 1
    '''
    return i + 1 < len(summaries) and summaries[i].field == summaries[i + 1].field


def generate_message(issues_to_summaries, args):
    '''
    Generates an email message by rendering a Jinja2 template.
    Loads and attaches necessary images for issue type and priority.
    '''
    message = MIMEMultipart('related')
    message['Subject'] = 'Jira Digest'
    message['From'] = args.email
    message['To'] = args.email

    attach_message_text(message, issues_to_summaries, args)
    attach_images(message, issues_to_summaries)
    return message


def attach_message_text(message, issues_to_summaries, args):
    '''
    Renders the Jinja2 email template, and attaches it to the
    message
    '''
    jinja_env = Environment(loader=FileSystemLoader('templates'))
    template = jinja_env.get_template('email.html')
    message_text = template.render(
        summarized_issues=issues_to_summaries,
        args=args
    )
    message.attach(MIMEText(message_text, 'html', 'utf-8'))


def attach_images(message, issues_to_summaries):
    '''
    Finds the images required from the issue summaries, loads
    them, and attaches them to the message
    '''
    images = get_images(issues_to_summaries)
    for image in images:
        attach_image(message, image)


def get_images(issues_to_summaries):
    '''
    Returns a list of issue type and priority names, which
    correspond to image files that will be attached to the email
    '''
    images = set()
    for issue, summaries in issues_to_summaries.iteritems():
        if len(summaries) > 0:
            # image filenames are lowercase
            images.add(issue.priority.lower())
            images.add(issue.type.lower())
    return images


def attach_image(message, cid):
    '''
    Looks for an image file with the name of the provided cid.
    Opens the file and attaches it to the message with the
    appropriate cid.
    '''
    filename = 'images/' + cid + '.png'
    try:
        fp = open(filename, 'rb')
        image = MIMEImage(fp.read(), _subtype='png')
        fp.close()
        image.add_header('Content-ID', '<' + cid + '>')
        message.attach(image)
    except IOError as e:
        print 'Failed to attach image for cid {cid}: {e}'.format(cid=cid, e=e)


def send_email(message, args):
    '''Sends the provided message using SendGrid SMTP
    '''
    s = smtplib.SMTP('smtp.sendgrid.net', 587)
    s.login(SMTP_USER, SMTP_PASS)
    s.sendmail(args.email, args.email, message.as_string())
    s.quit()


if __name__ == '__main__':
    main()
