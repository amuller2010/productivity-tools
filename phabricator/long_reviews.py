from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import smtplib

from jinja2 import Template
from phabricator import Phabricator


ALIASES = [
    'amuller',
    'barykin',
    'victor',
    'kuan',
    'farshid',
    'mallik',
    'jack',
    'tamara',
    'jasmine',
    'geoffrey',
    'patrick',
    'jacques',
    'elliot',
    'romulo'
]

MAX_DAYS = 7
MAX_DIFFS = 5

USER = ''
PASS = ''
EMAIL = ''
EMAIL_TEMPLATE = '''
{% macro format_review(review) %}
    <a href="{{ review.uri }}">D{{ review.id }}</a> | {{ review.dateString }} |
    {{ review.diffs|length }} diffs | {{ review.title }}
{% endmacro %}

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN">
<html lang="en">
<body>
    <h4>Long Code Reviews</h4>
    {% for user, reviews in users_to_reviews.iteritems() %}
        <p>{{ user|lower }}</p>
        <ul>
        {% for review in reviews %}
            <li>{{ format_review(review) }}</li>
        {% endfor %}
        </ul>
    {% endfor %}
</body>
</html>
'''


def find_user_ids(phab):
    users = phab.user.find(aliases=ALIASES)
    return users.response


def find_long_reviews(phab, aliases_to_user_ids):
    reviews = phab.differential.query(
        authors=aliases_to_user_ids.values(),
        status='status-open'
    )
    long_reviews = []
    cutoff_date = datetime.now() - timedelta(days=MAX_DAYS)
    for review in reviews:
        date_created = datetime.fromtimestamp(float(review['dateCreated']))
        if len(review['diffs']) > MAX_DIFFS or date_created < cutoff_date:
            review['dateString'] = date_created.strftime('%Y-%m-%d')
            long_reviews.append(review)
    return long_reviews


def email_report(aliases_to_user_ids, long_reviews):
    template = Template(EMAIL_TEMPLATE)
    message_text = template.render(
        users_to_reviews=map_users_to_reviews(aliases_to_user_ids, long_reviews)
    )
    message = MIMEText(message_text, 'html')
    message['Subject'] = 'Long Code Reviews'
    message['From'] = EMAIL
    message['To'] = EMAIL

    s = smtplib.SMTP('smtp.sendgrid.net', 587)
    s.login(USER, PASS)
    s.sendmail(EMAIL, EMAIL, message.as_string())
    s.quit()


def map_users_to_reviews(aliases_to_user_ids, reviews):
    user_ids_to_aliases = {v: k for k, v in aliases_to_user_ids.iteritems()}
    users_to_reviews = defaultdict(list)
    for review in reviews:
        user = user_ids_to_aliases[review['authorPHID']]
        users_to_reviews[user].append(review)
    return users_to_reviews


def main():
    phab = Phabricator()
    aliases_to_user_ids = find_user_ids(phab)
    long_reviews = find_long_reviews(phab, aliases_to_user_ids)
    email_report(aliases_to_user_ids, long_reviews)


if __name__ == "__main__":
    main()
